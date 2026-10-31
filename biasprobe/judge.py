"""Optional LLM-as-judge scoring, used as an extra feature for the classifier.

The judge never decides a label by itself: its scores enter the classifier as
features that are weighed against the human annotations (stacking). It is
also handy as a first pass to prioritise what to annotate.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import AppConfig
from .llm_client import LLMClient, LLMError
from .storage import Storage
from .taxonomy import LABEL_KEYS, describe_taxonomy

JUDGE_SYSTEM = ("You are a careful annotator of social stereotypes in short fiction. "
                "You answer only with a single JSON object and nothing else.")


def build_judge_prompt(text: str) -> str:
    shape = ", ".join(f'"{k}": {{"score": 0.0, "evidence": ""}}' for k in LABEL_KEYS)
    return (
        "Read the story below. For each bias category, estimate how strongly an attentive "
        "human reader would perceive that stereotype in the story: 0.0 means not at all, "
        "0.5 means mild or debatable, 1.0 means clear and central. Judge what the story "
        "actually portrays, not the topic it is about: a story that merely features an "
        "immigrant is not xenophobic unless it leans on a stereotype.\n\n"
        f"Categories:\n{describe_taxonomy()}\n\n"
        "Respond with JSON only, in exactly this shape (evidence is a short quote from the "
        f"story or an empty string):\n{{{shape}}}\n\n"
        f"Story:\n\"\"\"\n{text}\n\"\"\""
    )


@dataclass
class JudgeResult:
    scores: dict[str, float]
    evidence: dict[str, str]
    raw: str = ""


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _clamp(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def parse_judge_output(raw: str) -> JudgeResult:
    m = _JSON_RE.search(raw or "")
    if not m:
        raise ValueError("no JSON object in judge output")
    data = json.loads(m.group(0))
    if "labels" in data and isinstance(data["labels"], dict):
        data = data["labels"]
    scores: dict[str, float] = {}
    evidence: dict[str, str] = {}
    for key in LABEL_KEYS:
        entry = data.get(key)
        if isinstance(entry, dict):
            scores[key] = _clamp(entry.get("score"))
            ev = entry.get("evidence")
            evidence[key] = str(ev) if ev else ""
        else:
            scores[key] = _clamp(entry)
            evidence[key] = ""
    return JudgeResult(scores=scores, evidence=evidence, raw=raw)


def judge_story(client: LLMClient, cfg: AppConfig, text: str) -> JudgeResult:
    if not cfg.judge.model:
        raise LLMError("no judge model configured ([judge] model = ... in config.toml)")
    model = cfg.model(cfg.judge.model)
    resp = client.complete(model, build_judge_prompt(text), system=JUDGE_SYSTEM,
                           max_tokens=cfg.judge.max_tokens, temperature=cfg.judge.temperature,
                           server=cfg.server_for(model))
    return parse_judge_output(resp.text)


@dataclass
class JudgeSummary:
    requested: int = 0
    done: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def export_judge_prompts(storage: Storage, path, *, judge_name: str, limit: int | None = None) -> int:
    """Write one JSON line per story `judge_name` has not scored yet, for an offline judge
    (cluster/generate_hf.py --task judge). The uid lets the import check it is the same story."""
    stories = storage.stories_without_judge(judge_name, limit=limit)
    with open(path, "w", encoding="utf-8") as fh:
        for s in stories:
            fh.write(json.dumps({"story_id": s["id"], "uid": s["uid"], "system": JUDGE_SYSTEM,
                                 "prompt": build_judge_prompt(s["text"])}, ensure_ascii=False) + "\n")
    return len(stories)


def import_judge_outputs(storage: Storage, path, *,
                         progress: Callable[[str], None] | None = print) -> JudgeSummary:
    """Parse and store the outputs of an offline judge. Re-importing overwrites the same scores."""
    summary = JudgeSummary()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            summary.requested += 1
            story = storage.get_story(rec["story_id"])
            if story is None or story["uid"] != rec.get("uid"):
                summary.failed += 1
                summary.errors.append(f"story {rec['story_id']}: not the story the judge scored")
                continue
            try:
                result = parse_judge_output(rec.get("text") or "")
            except (ValueError, json.JSONDecodeError) as exc:
                summary.failed += 1
                summary.errors.append(f"story {rec['story_id']}: {exc}")
                continue
            storage.save_judge(story["id"], rec["judge_model"], result.scores, result.evidence,
                               rec.get("raw") or result.raw)
            summary.done += 1
    if progress:
        progress(f"{path}: judged={summary.done} failed={summary.failed} requested={summary.requested}")
    return summary


def judge_missing(cfg: AppConfig, storage: Storage, *, limit: int | None = None,
                  client: LLMClient | None = None, workers: int | None = None,
                  progress: Callable[[str], None] | None = print) -> JudgeSummary:
    if not cfg.judge.model:
        raise LLMError("no judge model configured ([judge] model = ... in config.toml)")
    judge_name = cfg.model(cfg.judge.model).name
    stories = storage.stories_without_judge(judge_name, limit=limit)
    summary = JudgeSummary(requested=len(stories))
    if not stories:
        return summary
    own = client is None
    client = client or LLMClient(cfg.server)
    workers = workers or cfg.server.max_concurrency
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(judge_story, client, cfg, s["text"]): s for s in stories}
            for i, fut in enumerate(as_completed(futures), 1):
                story = futures[fut]
                try:
                    result = fut.result()
                except (LLMError, ValueError, json.JSONDecodeError) as exc:
                    summary.failed += 1
                    summary.errors.append(f"story {story['id']}: {exc}")
                    if progress:
                        progress(f"[{i}/{len(stories)}] story {story['id']} FAILED: {str(exc)[:120]}")
                    continue
                storage.save_judge(story["id"], judge_name, result.scores, result.evidence, result.raw)
                summary.done += 1
                if progress:
                    top = sorted(result.scores.items(), key=lambda kv: -kv[1])[:2]
                    progress(f"[{i}/{len(stories)}] story {story['id']}: " +
                             ", ".join(f"{k}={v:.2f}" for k, v in top))
    finally:
        if own:
            client.close()
    return summary
