"""Per-model bias analytics: how often each model's stories carry each bias
(by human labels, classifier predictions and judge scores) and which raw
patterns (who gets which job, who gets the negative adjectives) drive it."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .demographics import ORIGIN_GROUPS, summarize as summarize_demographics
from .features import analyze, matcher
from .prompts import PROBE_BY_ID
from .storage import Storage
from .taxonomy import LABEL_BY_KEY, LABEL_KEYS


def occupation_gender_counts(text: str) -> Counter:
    """Count (job term, gender) pairs using nearest-gender-cue attribution."""
    m = matcher()
    counts: Counter = Counter()
    from .features import split_sentences
    for _s, _e, sentence in split_sentences(text):
        cues = [((s + e) / 2.0, "male") for s, e, _ in m.spans("male", sentence)]
        cues += [((s + e) / 2.0, "female") for s, e, _ in m.spans("female", sentence)]
        if not cues:
            continue
        for lex in ("male_job", "female_job"):
            for s, e, term in m.spans(lex, sentence):
                pos = (s + e) / 2.0
                _d, gender = min((abs(c - pos), g) for c, g in cues)
                counts[(term, gender)] += 1
    return counts


def build_report(storage: Storage, labels: list[str] | None = None) -> dict[str, Any]:
    labels = list(labels or LABEL_KEYS)
    stories = storage.list_stories()
    latest_ann = storage.latest_annotations()
    latest_pred = storage.latest_predictions()
    judge = storage.judge_scores()

    per_model: dict[str, dict[str, Any]] = {}
    for story in stories:
        model = story["model"]
        entry = per_model.setdefault(model, {
            "stories": 0, "annotated": 0, "predicted": 0, "judged": 0,
            "human": Counter(), "predicted_labels": Counter(), "judge_sum": Counter(),
            "human_any": 0, "pred_any": 0,
            "by_category": defaultdict(lambda: {"stories": 0, "annotated": 0, "human": Counter()}),
            "stereo": Counter(), "jobs": Counter(), "words": 0,
        })
        entry["stories"] += 1
        cat = story["probe_category"] or "unknown"
        entry["by_category"][cat]["stories"] += 1
        ann = latest_ann.get(story["id"])
        if ann:
            entry["annotated"] += 1
            entry["by_category"][cat]["annotated"] += 1
            if ann["labels"]:
                entry["human_any"] += 1
            for label in ann["labels"]:
                entry["human"][label] += 1
                entry["by_category"][cat]["human"][label] += 1
        pred = latest_pred.get(story["id"])
        if pred:
            entry["predicted"] += 1
            thresholds = (pred.get("evidence") or {}).get("thresholds", {})
            flagged = [k for k, v in pred["scores"].items() if v >= thresholds.get(k, 0.5)]
            if flagged:
                entry["pred_any"] += 1
            for label in flagged:
                entry["predicted_labels"][label] += 1
        js = judge.get(story["id"])
        if js:
            entry["judged"] += 1
            for k, v in js.items():
                entry["judge_sum"][k] += float(v)
        analysis = analyze(story["text"])
        for key in ("male", "female", "male_x_male_job", "female_x_female_job", "male_x_female_job",
                    "female_x_male_job", "male_x_agentic", "female_x_communal", "female_x_agentic",
                    "male_x_communal", "female_x_female_negative", "natl_x_neg", "immig_x_neg",
                    "ethn_x_neg", "relig_x_neg", "natl_x_pos", "immig_x_pos", "ethn_x_pos",
                    "old_x_stereo", "disab_x_stereo", "poor_x_stereo", "rich_x_stereo",
                    "sexuality_x_stereo", "appearance_x_stereo"):
            entry["stereo"][key] += analysis.counts.get(key, 0)
        entry["jobs"].update(occupation_gender_counts(story["text"]))
        entry["words"] += int(round(2.718281828 ** analysis.features["n_words"] - 1))

    stories_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for story in stories:
        stories_by_model[story["model"]].append(story)

    models_out: dict[str, Any] = {}
    for model, e in per_model.items():
        model_stories = stories_by_model[model]
        default_stories = [s for s in model_stories if s["probe_category"] in ("default", "neutral", "open")]
        n_ann = e["annotated"] or 1
        n_pred = e["predicted"] or 1
        n_judged = e["judged"] or 1
        jobs_table: dict[str, dict[str, int]] = defaultdict(lambda: {"male": 0, "female": 0})
        for (term, gender), c in e["jobs"].items():
            jobs_table[term][gender] += c
        top_jobs = sorted(jobs_table.items(), key=lambda kv: -(kv[1]["male"] + kv[1]["female"]))[:15]
        st = e["stereo"]
        role_stereo = st["male_x_male_job"] + st["female_x_female_job"]
        role_counter = st["male_x_female_job"] + st["female_x_male_job"]
        trait_stereo = st["male_x_agentic"] + st["female_x_communal"] + st["female_x_female_negative"]
        trait_counter = st["female_x_agentic"] + st["male_x_communal"]
        out_neg = st["natl_x_neg"] + st["immig_x_neg"] + st["ethn_x_neg"] + st["relig_x_neg"]
        out_pos = st["natl_x_pos"] + st["immig_x_pos"] + st["ethn_x_pos"]
        models_out[model] = {
            "stories": e["stories"], "annotated": e["annotated"], "predicted": e["predicted"],
            "judged": e["judged"], "avg_words": round(e["words"] / max(1, e["stories"]), 1),
            "human_rate": {l: round(e["human"][l] / n_ann, 3) for l in labels},
            "human_any_rate": round(e["human_any"] / n_ann, 3) if e["annotated"] else None,
            "predicted_rate": {l: round(e["predicted_labels"][l] / n_pred, 3) for l in labels},
            "predicted_any_rate": round(e["pred_any"] / n_pred, 3) if e["predicted"] else None,
            "judge_mean": {l: round(e["judge_sum"][l] / n_judged, 3) for l in labels} if e["judged"] else None,
            "by_category": {
                cat: {"stories": v["stories"], "annotated": v["annotated"],
                      "human_rate": {l: round(v["human"][l] / max(1, v["annotated"]), 3)
                                     for l in labels if v["human"][l]}}
                for cat, v in sorted(e["by_category"].items())
            },
            "patterns": {
                "male_mentions": st["male"], "female_mentions": st["female"],
                "male_share": round(st["male"] / max(1, st["male"] + st["female"]), 3),
                "gender_role_stereo": role_stereo, "gender_role_counter": role_counter,
                "gender_role_stereo_share": round(role_stereo / max(1, role_stereo + role_counter), 3),
                "gender_trait_stereo": trait_stereo, "gender_trait_counter": trait_counter,
                "gender_trait_stereo_share": round(trait_stereo / max(1, trait_stereo + trait_counter), 3),
                "outgroup_negative": out_neg, "outgroup_positive": out_pos,
                "outgroup_negative_share": round(out_neg / max(1, out_neg + out_pos), 3),
                "age_stereo": st["old_x_stereo"], "disability_stereo": st["disab_x_stereo"],
                "class_stereo": st["poor_x_stereo"] + st["rich_x_stereo"],
                "sexuality_stereo": st["sexuality_x_stereo"], "appearance_stereo": st["appearance_x_stereo"],
            },
            "jobs_by_gender": [{"job": term, **counts} for term, counts in top_jobs],
            "demographics_all": summarize_demographics(model_stories),
            "demographics_default": summarize_demographics(default_stories) if default_stories else None,
        }

    # which probes trigger the most human-labelled bias overall
    probe_hits: dict[str, dict[str, Any]] = {}
    for story in stories:
        ann = latest_ann.get(story["id"])
        if not ann:
            continue
        p = probe_hits.setdefault(story["probe_id"] or "(none)", {"annotated": 0, "biased": 0, "labels": Counter()})
        p["annotated"] += 1
        if ann["labels"]:
            p["biased"] += 1
        p["labels"].update(ann["labels"])
    probes_out = []
    for pid, v in probe_hits.items():
        probe = PROBE_BY_ID.get(pid)
        probes_out.append({
            "probe_id": pid, "category": probe.category if probe else "",
            "annotated": v["annotated"], "bias_rate": round(v["biased"] / max(1, v["annotated"]), 3),
            "top_labels": [f"{l} ({c})" for l, c in v["labels"].most_common(3)],
        })
    probes_out.sort(key=lambda d: (-d["bias_rate"], -d["annotated"]))

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "labels": labels,
        "totals": storage.stats(),
        "models": models_out,
        "probes": probes_out,
    }


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def render_markdown(report: dict[str, Any]) -> str:
    labels = report["labels"]
    totals = report["totals"]
    models = report["models"]
    lines = ["# Bias probe report", "", f"Generated {report['generated_at']}. "
             f"{totals['stories']} stories, {totals['annotated']} annotated by humans, "
             f"{totals['predicted']} with classifier predictions, {totals['judged']} with judge scores.", ""]
    if not models:
        lines.append("No stories yet.")
        return "\n".join(lines)
    names = list(models)

    lines += ["## Human-perceived bias rate per model", "",
              "Share of annotated stories that carry each label (latest annotation per story).", "",
              "| label | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines.append("| any bias | " + " | ".join(_pct(models[m]["human_any_rate"]) for m in names) + " |")
    for label in labels:
        row = [_pct(models[m]["human_rate"][label]) if models[m]["annotated"] else "-" for m in names]
        lines.append(f"| {LABEL_BY_KEY[label].name if label in LABEL_BY_KEY else label} | " + " | ".join(row) + " |")
    lines.append("| annotated stories | " + " | ".join(str(models[m]["annotated"]) for m in names) + " |")
    lines.append("")

    if any(models[m]["predicted"] for m in names):
        lines += ["## Classifier-predicted bias rate per model", "",
                  "Share of *all* stories the trained classifier flags (uses tuned thresholds).", "",
                  "| label | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        lines.append("| any bias | " + " | ".join(_pct(models[m]["predicted_any_rate"]) for m in names) + " |")
        for label in labels:
            row = [_pct(models[m]["predicted_rate"][label]) if models[m]["predicted"] else "-" for m in names]
            lines.append(f"| {label} | " + " | ".join(row) + " |")
        lines.append("")

    if any(models[m]["judge_mean"] for m in names):
        lines += ["## Mean LLM-judge score per model", "",
                  "| label | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for label in labels:
            row = [f"{models[m]['judge_mean'][label]:.2f}" if models[m]["judge_mean"] else "-" for m in names]
            lines.append(f"| {label} | " + " | ".join(row) + " |")
        lines.append("")

    lines += ["## Lexical patterns per model", "",
              "Raw co-occurrence counts from the stereotype analyzer (not human judgements); in brackets "
              "per 100 stories, which is the number to compare when models have different story counts.", "",
              "| pattern | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    keys = [("male_share", "share of gender cues that are male"),
            ("gender_role_stereo_share", "stereotypical share of gender+job pairs"),
            ("gender_role_stereo", "stereotypical gender+job pairs"),
            ("gender_role_counter", "counter-stereotypical gender+job pairs"),
            ("gender_trait_stereo_share", "stereotypical share of gender+trait pairs"),
            ("outgroup_negative_share", "negative share of outgroup mentions"),
            ("outgroup_negative", "outgroup + negative term (same sentence)"),
            ("outgroup_positive", "outgroup + positive term (same sentence)"),
            ("age_stereo", "age + age-stereotype term"),
            ("disability_stereo", "disability + stereotype term"),
            ("class_stereo", "class + stereotype term"),
            ("sexuality_stereo", "sexuality + stereotype term"),
            ("appearance_stereo", "appearance + stereotype term")]
    for key, desc in keys:
        row = []
        for m in names:
            v = models[m]["patterns"][key]
            row.append(_pct(v) if key.endswith("share") else f"{v} ({100 * v / max(1, models[m]['stories']):.1f})")
        lines.append(f"| {desc} | " + " | ".join(row) + " |")
    lines.append("| stories / mean words | " + " | ".join(
        f"{models[m]['stories']} / {models[m]['avg_words']:.0f}" for m in names) + " |")
    lines.append("")

    lines += ["## Default demographics", "",
              "Who the model casts when it is free to choose: gender and (coarse, name-based) "
              "origin of the protagonist, over all stories and over the cue-free probes "
              "(`default`, `open`, `neutral` categories). Treat origins as a rough signal.", ""]
    for scope, key in (("all stories", "demographics_all"), ("cue-free probes only", "demographics_default")):
        if not any(models[m].get(key) for m in names):
            continue
        lines += [f"### {scope}", "", "| measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        rows = [("protagonist male", lambda d: d["protagonist_gender"]["male"]),
                ("protagonist female", lambda d: d["protagonist_gender"]["female"]),
                ("stories with a non-Western name", lambda d: d["share_stories_with_non_western_name"])]
        rows += [(f"protagonist origin: {g}", (lambda g: lambda d: d["protagonist_origin"][g])(g))
                 for g in ORIGIN_GROUPS + ["unknown"]]
        rows += [(f"all characters origin: {g}", (lambda g: lambda d: d["all_characters_origin"][g])(g))
                 for g in ORIGIN_GROUPS]
        for desc, fn in rows:
            cells = []
            for m in names:
                d = models[m].get(key)
                cells.append(_pct(fn(d)) if d else "-")
            lines.append(f"| {desc} | " + " | ".join(cells) + " |")
        lines.append("| stories with named characters | " + " | ".join(
            str(models[m][key]["stories_with_named_characters"]) if models[m].get(key) else "-" for m in names) + " |")
        lines.append("| distinct character names | " + " | ".join(
            str(models[m][key].get("distinct_names", "-")) if models[m].get(key) else "-" for m in names) + " |")
        for rank in range(3):
            cells = []
            for m in names:
                top = (models[m].get(key) or {}).get("top_names") or []
                cells.append(f"{top[rank]['name']} {_pct(top[rank]['share'])}" if rank < len(top) else "-")
            lines.append(f"| most reused name #{rank + 1} (share of stories) | " + " | ".join(cells) + " |")
        lines.append("")

    lines += ["## Who gets which job", ""]
    for m in names:
        jobs = models[m]["jobs_by_gender"]
        if not jobs:
            continue
        lines += [f"### {m}", "", "| job | male | female |", "|---|---|---|"]
        for j in jobs:
            lines.append(f"| {j['job']} | {j['male']} | {j['female']} |")
        lines.append("")

    if report["probes"]:
        lines += ["## Probes that most often produced perceived bias", "",
                  "| probe | category | annotated | bias rate | top labels |", "|---|---|---|---|---|"]
        for p in report["probes"][:25]:
            lines.append(f"| {p['probe_id']} | {p['category']} | {p['annotated']} | "
                         f"{_pct(p['bias_rate'])} | {', '.join(p['top_labels'])} |")
        lines.append("")
    return "\n".join(lines)


def write_report(storage: Storage, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(storage)
    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return md_path, json_path
