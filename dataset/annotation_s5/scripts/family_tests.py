"""Family comparisons in the balanced round that respect the shared premises.

usage (from the repository folder): PYTHONPATH=. python dataset/annotation_s5/scripts/family_tests.py
Every model wrote about the same 89 premises, so stories are not independent. The interval here
resamples premises (10,000 times) rather than stories. Also prints rates by premise category and
how the LLM judge, which is not a Claude model, ranks the same stories.
"""
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from biasprobe.storage import Storage  # noqa: E402
from biasprobe.taxonomy import LABEL_KEYS  # noqa: E402

FAMILIES = {"Claude": ["claude-haiku-single", "claude-sonnet-single", "claude-opus-single"],
            "Gemma": ["gemma-4-e4b-it"], "Qwen3.5": ["qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"],
            "Mistral": ["mistral-7b-instruct-v0.3"], "OLMo": ["olmo-3-7b-instruct", "olmo-3.1-32b-instruct"],
            "gpt-oss": ["gpt-oss-20b"]}
OPEN = [m for f, ms in FAMILIES.items() if f != "Claude" for m in ms]
mapping = json.loads((ROOT / "mapping.json").read_text("utf-8"))
results = {r["id"]: r for f in (ROOT / "results").glob("batch_*.json") for r in json.loads(f.read_text("utf-8"))}
st = Storage("data/biasprobe.db")
judge = st.judge_scores("phi-4")

rows = []
for anon, it in mapping.items():
    if it["role"] != "target":
        continue
    rec = results[anon]
    labels = {x for x in rec["labels"] if x in LABEL_KEYS}
    casting = {c.get("label") for c in rec.get("casting", [])} & labels
    story = st.get_story(it["story_id"])
    rows.append({"model": it["model"], "probe": it["probe_id"], "category": story["probe_category"],
                 "any": bool(labels), "beyond": bool(labels - casting), "casting": bool(casting),
                 "judge": max(judge[it["story_id"]].values()) >= 0.5 if it["story_id"] in judge else None})


def rate(items, key):
    return sum(r[key] for r in items) / len(items) if items else float("nan")


by_probe = defaultdict(list)
for r in rows:
    by_probe[r["probe"]].append(r)
probes = sorted(by_probe)
rng = random.Random(1234)


def diff(sample, key, group):
    a = [r for p in sample for r in by_probe[p] if r["model"] in group]
    b = [r for p in sample for r in by_probe[p] if r["model"] in FAMILIES["Claude"]]
    return rate(a, key) - rate(b, key)


draws = [[rng.choice(probes) for _ in probes] for _ in range(10000)]
print("| vs Claude, resampling premises (95%) | any label | beyond casting | any casting |\n|---|---|---|---|")
for name, group in [("all open", OPEN)] + [(f, ms) for f, ms in FAMILIES.items() if f != "Claude"]:
    cells = []
    for key in ("any", "beyond", "casting"):
        vals = sorted(diff(d, key, group) for d in draws)
        cells.append(f"{diff(probes, key, group) * 100:+.0f} ({vals[250] * 100:+.0f} to {vals[9750] * 100:+.0f})")
    print(f"| {name} | " + " | ".join(cells) + " |")

cats = defaultdict(lambda: defaultdict(list))
for r in rows:
    cats[r["category"]]["Claude" if r["model"] in FAMILIES["Claude"] else "open"].append(r)
print("\n| premise category | Claude any | open any | Claude beyond | open beyond |\n|---|---|---|---|---|")
for c, v in sorted(cats.items(), key=lambda kv: -rate(kv[1]["open"], "beyond")):
    print(f"| {c} | {rate(v['Claude'], 'any'):.0%} | {rate(v['open'], 'any'):.0%} "
          f"| {rate(v['Claude'], 'beyond'):.0%} | {rate(v['open'], 'beyond'):.0%} |")

print("\n| family | readers: beyond casting | Phi-4 judge: any score >= 0.5 |\n|---|---|---|")
for f, ms in FAMILIES.items():
    items = [r for r in rows if r["model"] in ms]
    judged = [r for r in items if r["judge"] is not None]
    print(f"| {f} | {rate(items, 'beyond'):.0%} | {rate(judged, 'judge'):.0%} ({len(judged)}) |")

per_probe = {p: rate(by_probe[p], "any") for p in probes}
print("\npremises labelled for 10+ of 11 models:", [p for p in probes if sum(r["any"] for r in by_probe[p]) >= 10])
print("premises labelled for no model:", [p for p in probes if sum(r["any"] for r in by_probe[p]) == 0])
