"""Generate stories from every configured model for every probe, resumably."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from .config import AppConfig, ModelConfig
from .llm_client import LLMClient, LLMError
from .prompts import Probe, select_probes
from .storage import Storage

SYSTEM_PROMPT = "You are a creative fiction writer. You write vivid, concrete short stories."

_TITLE_LINE = re.compile(r"^\s*(?:\*\*|#+\s*|title\s*:\s*)[^\n]{0,80}(?:\*\*)?\s*$", re.IGNORECASE)
# Reasoning blocks of thinking models: Qwen/DeepSeek <think>, Gemma 4 <|channel>thought...<channel|>.
_REASONING = re.compile(r"<think>.*?(?:</think>|$)|<\|channel>.*?(?:<channel\|>|$)", re.DOTALL)


def clean_story(text: str) -> str:
    """Strip reasoning blocks, a leading title line, wrapping quotes/code fences and trailing notes."""
    text = _REASONING.sub("", text)
    text = text.split("</think>")[-1].strip()
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text).strip()
    lines = text.split("\n")
    if len(lines) > 1 and _TITLE_LINE.match(lines[0]) and len(lines[0]) < 80:
        lines = lines[1:]
    text = "\n".join(lines).strip()
    if len(text) > 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    return text


@dataclass
class GenerationJob:
    model: ModelConfig
    probe: Probe
    sample_index: int
    prompt: str


@dataclass
class GenerationSummary:
    requested: int = 0
    generated: int = 0
    duplicates: int = 0
    failed: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"requested={self.requested} generated={self.generated} duplicates={self.duplicates} "
                f"failed={self.failed} skipped_existing={self.skipped_existing}")


def plan_jobs(cfg: AppConfig, storage: Storage, *, probes: list[Probe] | None = None,
              models: list[ModelConfig] | None = None, samples: int | None = None,
              words: int | None = None) -> tuple[list[GenerationJob], int]:
    """Build the list of (model, probe, sample) calls that are still missing."""
    probes = probes if probes is not None else select_probes(cfg.generation.categories)
    models = models if models is not None else cfg.models
    samples = samples or cfg.generation.stories_per_prompt
    words = words or cfg.generation.target_words
    jobs: list[GenerationJob] = []
    skipped = 0
    for model in models:
        for probe in probes:
            have = storage.existing_count(model.name, probe.id)
            skipped += min(have, samples)
            for k in range(have, samples):
                jobs.append(GenerationJob(model, probe, k, probe.build(words)))
    return jobs, skipped


def run_generation(cfg: AppConfig, storage: Storage, *, probes: list[Probe] | None = None,
                   models: list[ModelConfig] | None = None, samples: int | None = None,
                   words: int | None = None, client: LLMClient | None = None,
                   workers: int | None = None, progress: Callable[[str], None] | None = print,
                   dry_run: bool = False) -> GenerationSummary:
    jobs, skipped = plan_jobs(cfg, storage, probes=probes, models=models, samples=samples, words=words)
    summary = GenerationSummary(requested=len(jobs), skipped_existing=skipped)
    if dry_run or not jobs:
        if progress:
            progress(f"{len(jobs)} generations planned ({skipped} already present)")
        return summary

    own_client = client is None
    client = client or LLMClient(cfg.server)
    workers = workers or cfg.server.max_concurrency
    gen = cfg.generation

    def work(job: GenerationJob):
        server = cfg.server_for(job.model)
        resp = client.complete(job.model, job.prompt, system=SYSTEM_PROMPT,
                               max_tokens=gen.max_tokens, temperature=gen.temperature, server=server)
        return job, resp

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(work, job) for job in jobs]
            for i, fut in enumerate(as_completed(futures), 1):
                try:
                    job, resp = fut.result()
                except LLMError as exc:
                    summary.failed += 1
                    summary.errors.append(str(exc))
                    if progress:
                        progress(f"[{i}/{len(jobs)}] FAILED: {str(exc)[:160]}")
                    continue
                except Exception as exc:  # noqa: BLE001 - keep the batch alive
                    summary.failed += 1
                    summary.errors.append(repr(exc))
                    if progress:
                        progress(f"[{i}/{len(jobs)}] ERROR: {exc!r}")
                    continue
                text = clean_story(resp.text)
                if len(text.split()) < 20:
                    summary.failed += 1
                    summary.errors.append(f"{job.model.name}/{job.probe.id}: output too short")
                    if progress:
                        progress(f"[{i}/{len(jobs)}] {job.model.name} {job.probe.id}: too short, skipped")
                    continue
                sid = storage.add_story(
                    text, job.model.name, probe_id=job.probe.id, probe_category=job.probe.category,
                    prompt=job.prompt, source="llm",
                    meta={"sample_index": job.sample_index, "latency_s": round(resp.latency_s, 2),
                          "usage": resp.usage, "attempts": resp.attempts,
                          "params": resp.request_params, "targets": list(job.probe.targets)})
                if sid is None:
                    summary.duplicates += 1
                    if progress:
                        progress(f"[{i}/{len(jobs)}] {job.model.name} {job.probe.id}: duplicate")
                else:
                    summary.generated += 1
                    if progress:
                        progress(f"[{i}/{len(jobs)}] {job.model.name} {job.probe.id} -> story {sid} "
                                 f"({len(text.split())} words, {resp.latency_s:.1f}s)")
    finally:
        if own_client:
            client.close()
    return summary


# ------------------------------------------------- offline (cluster) generation

def export_prompts(path, probes: list[Probe], *, words: int = 250) -> int:
    """Write one JSON line per probe for an offline generator (cluster/generate_hf.py)."""
    import json
    with open(path, "w", encoding="utf-8") as fh:
        for probe in probes:
            fh.write(json.dumps({"probe_id": probe.id, "probe_category": probe.category,
                                 "targets": list(probe.targets), "system": SYSTEM_PROMPT,
                                 "prompt": probe.build(words)}, ensure_ascii=False) + "\n")
    return len(probes)


def import_generations(storage: Storage, path, *, progress: Callable[[str], None] | None = print,
                       ) -> GenerationSummary:
    """Load stories written by an offline generator, cleaned and filtered like `run_generation`.
    Re-importing the same file is a no-op (identical stories are dropped)."""
    import json
    from .prompts import PROBE_BY_ID
    summary = GenerationSummary()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            summary.requested += 1
            label = f"{rec.get('model')}/{rec.get('probe_id')}#{rec.get('sample_index')}"
            text = clean_story(rec.get("text") or rec.get("raw") or "")
            if len(text.split()) < 20:
                summary.failed += 1
                summary.errors.append(f"{label}: output too short")
                continue
            probe = PROBE_BY_ID.get(rec.get("probe_id", ""))
            meta = {k: rec[k] for k in ("sample_index", "latency_s", "params", "finished", "engine",
                                        "model_path", "generation") if k in rec}
            meta["usage"] = {"completion_tokens": rec.get("new_tokens")}
            meta["targets"] = list(probe.targets) if probe else rec.get("targets", [])
            sid = storage.add_story(text, rec["model"], probe_id=rec.get("probe_id", ""),
                                    probe_category=rec.get("probe_category") or (probe.category if probe else ""),
                                    prompt=rec.get("prompt", ""), source=rec.get("source", "llm"), meta=meta,
                                    created_at=rec.get("created_at"))
            if sid is None:
                summary.duplicates += 1
            else:
                summary.generated += 1
    if progress:
        progress(f"{path}: {summary}")
    return summary
