"""Human-perceived bias rates on the matched probe set (one story per probe per model):
Claude with round-3 labels (and study-1 labels for reference), open models with round-2 labels.

usage (from the project folder): PYTHONPATH=. python dataset/annotation_s3/scripts/rates.py
"""
import math
from collections import Counter, defaultdict

from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS

st = Storage("data/biasprobe.db")
CLAUDE = ["claude-haiku", "claude-sonnet", "claude-opus"]
OPEN = ["gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"]


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def matched(model):
    first = {}
    for s in sorted(st.list_stories(model=model), key=lambda s: s["id"]):
        first.setdefault(s["probe_id"], s)
    return list(first.values())


def labels_by(stories, prefix=None, exclude=None):
    """story -> (labels, notes) from the latest annotation whose annotator starts with `prefix`
    (or, with `exclude`, the latest one that does not)."""
    out = []
    for s in stories:
        anns = st.annotations_for(s["id"])
        if prefix:
            anns = [a for a in anns if a["annotator"].startswith(prefix)]
        if exclude:
            anns = [a for a in anns if not a["annotator"].startswith(exclude)]
        if anns:
            out.append((s, set(anns[-1]["labels"]), anns[-1]["notes"]))
    return out


cols = {}
for m in CLAUDE:
    cols[m] = labels_by(matched(m), prefix="annotator-s3-")
for m in OPEN:
    cols[m] = labels_by(matched(m), prefix="annotator-s2-")
for m in CLAUDE:
    cols[m + " (study 1)"] = labels_by(matched(m), exclude="annotator-s3-")

rows = defaultdict(list)
for name, data in cols.items():
    n = len(data); labs = [l for _, l, _ in data]
    k = sum(bool(l) for l in labs); lo, hi = wilson(k, n)
    rows["n"].append(str(n))
    rows["any bias"].append(f"{100 * k / n:.0f}% ({100 * lo:.0f}–{100 * hi:.0f})")
    for lab in LABEL_KEYS:
        rows[lab].append(f"{100 * sum(lab in l for l in labs) / n:.0f}%")
    rows["labels per story"].append(f"{sum(len(l) for l in labs) / n:.2f}")
    cast = sum(bool(l) and notes.lower().startswith("casting only") for _, l, notes in data)
    rows["casting-only share"].append(f"{100 * cast / max(1, k):.0f}%")
print("| measure | " + " | ".join(cols) + " |")
for key, vals in rows.items():
    if key in LABEL_KEYS and all(v == "0%" for v in vals):
        continue
    print(f"| {key} | " + " | ".join(vals) + " |")

print()
for name, group in (("Claude round 3", CLAUDE), ("Claude study 1", [m + " (study 1)" for m in CLAUDE]),
                    ("open round 2", OPEN)):
    labs = [l for m in group for _, l, _ in cols[m]]
    k = sum(bool(l) for l in labs); lo, hi = wilson(k, len(labs))
    print(f"{name}: {k}/{len(labs)} = {100 * k / len(labs):.0f}% ({100 * lo:.0f}–{100 * hi:.0f}); "
          + ", ".join(f"{lab} {100 * sum(lab in l for l in labs) / len(labs):.0f}%"
                      for lab in ("gender_role", "gender_trait", "racial_ethnic", "xenophobia", "age")))

# two-proportion z test, pooled Claude round 3 vs open round 2
a = [bool(l) for m in CLAUDE for _, l, _ in cols[m]]; b = [bool(l) for m in OPEN for _, l, _ in cols[m]]
p1, p2 = sum(a) / len(a), sum(b) / len(b); p = (sum(a) + sum(b)) / (len(a) + len(b))
z = (p2 - p1) / math.sqrt(p * (1 - p) * (1 / len(a) + 1 / len(b)))
print(f"z = {z:.2f} (open minus Claude = {100 * (p2 - p1):.1f} points)")

print("\n| category | Claude (round 3) | open models (round 2) |\n|---|---|---|")
cat = defaultdict(lambda: {"c": [0, 0], "o": [0, 0], "cl": Counter(), "ol": Counter()})
for grp, ms in (("c", CLAUDE), ("o", OPEN)):
    for m in ms:
        for s, l, _ in cols[m]:
            c = cat[s["probe_category"]]; c[grp][0] += 1; c[grp][1] += bool(l); c[grp + "l"].update(l)
for k, v in sorted(cat.items(), key=lambda kv: -kv[1]["o"][1] / max(1, kv[1]["o"][0])):
    print(f"| {k} | {v['c'][1]}/{v['c'][0]} ({100 * v['c'][1] / max(1, v['c'][0]):.0f}%) | "
          f"{v['o'][1]}/{v['o'][0]} ({100 * v['o'][1] / max(1, v['o'][0]):.0f}%) |")
print("\nracial_ethnic labels on race/class/default probes: Claude",
      sum(cat[c]["cl"]["racial_ethnic"] for c in ("race", "class", "default")),
      "| open", sum(cat[c]["ol"]["racial_ethnic"] for c in ("race", "class", "default")))
print("gender_role on default probes: Claude", cat["default"]["cl"]["gender_role"], "/", cat["default"]["c"][0],
      "| open", cat["default"]["ol"]["gender_role"], "/", cat["default"]["o"][0])

hits = defaultdict(list)
for m in CLAUDE:
    for s, l, _ in cols[m]:
        hits[s["probe_id"]].append(l)
print("\nprobes labelled for all 3 Claude models (round 3):", sorted(p for p, v in hits.items() if all(v)))

# --- within-round comparisons via the hidden anchors -------------------------------------
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
res2 = {r["id"]: r for f in (ROOT / "annotation_s2" / "results").glob("*.json") for r in json.loads(f.read_text("utf-8"))}
map2 = json.loads((ROOT / "annotation_s2" / "mapping.json").read_text("utf-8"))
res3 = {r["id"]: r for f in (ROOT / "annotation_s3" / "results").glob("*.json") for r in json.loads(f.read_text("utf-8"))}
map3 = json.loads((ROOT / "annotation_s3" / "mapping.json").read_text("utf-8"))

# round 2: Claude anchors (random sample of 30) next to the open-model targets
c2 = [bool(res2[t]["labels"]) for t, v in map2.items() if v["role"] == "anchor"]
lo, hi = wilson(sum(c2), len(c2))
print(f"\nwithin round 2: Claude anchors {sum(c2)}/{len(c2)} = {100 * sum(c2) / len(c2):.0f}% ({100 * lo:.0f}–{100 * hi:.0f})"
      f" vs open targets 146/356 = 41%")

# round 3: open anchors (5 round-2-labelled + 5 round-2-clean per model), reweighted to each model's round-2 rate
s2_rate = {m: sum(bool(l) for _, l, _ in cols[m]) / len(cols[m]) for m in OPEN}
strata = defaultdict(lambda: {True: [], False: []})
for t, v in map3.items():
    if v["role"] == "anchor":
        r2 = [a for a in st.annotations_for(v["story_id"]) if a["annotator"].startswith("annotator-s2-")][-1]
        strata[v["model"]][bool(r2["labels"])].append(bool(res3[t]["labels"]))


def estimate(strata):
    return sum(s2_rate[m] * sum(s[True]) / len(s[True]) + (1 - s2_rate[m]) * sum(s[False]) / len(s[False])
               for m, s in strata.items()) / len(strata)


est = estimate(strata)
rng = random.Random(0); boots = []
for _ in range(4000):
    bs = {m: {k: [rng.choice(v) for _ in v] for k, v in s.items()} for m, s in strata.items()}
    boots.append(estimate(bs))
boots.sort()
print(f"within round 3: open models (reweighted anchors) {100 * est:.0f}% "
      f"(bootstrap 95% {100 * boots[100]:.0f}–{100 * boots[3899]:.0f}) vs Claude targets 94/267 = 35%")
for m, s in strata.items():
    print(f"  {m}: round-2 labelled anchors relabelled {sum(s[True])}/{len(s[True])}, "
          f"round-2 clean anchors labelled {sum(s[False])}/{len(s[False])}")

# --- stricter measure: stories whose labels are more than casting ------------------------
print("\nstories with a stereotype beyond casting (labelled, note does not start 'Casting only'):")
for name, group in (("Claude round 3", CLAUDE), ("Claude study 1", [m + " (study 1)" for m in CLAUDE]),
                    ("open round 2", OPEN)):
    data = [x for m in group for x in cols[m]]
    k = sum(bool(l) and not n.lower().startswith("casting only") for _, l, n in data)
    lo, hi = wilson(k, len(data))
    per = ", ".join(f"{m.split(' ')[0]} {100 * sum(bool(l) and not n.lower().startswith('casting only') for _, l, n in cols[m]) / len(cols[m]):.0f}%"
                    for m in group)
    print(f"  {name}: {k}/{len(data)} = {100 * k / len(data):.0f}% ({100 * lo:.0f}–{100 * hi:.0f}); {per}")
c2s = [bool(res2[t]["labels"]) and not res2[t]["notes"].lower().startswith("casting only")
       for t, v in map2.items() if v["role"] == "anchor"]
print(f"  within round 2, Claude anchors beyond casting: {sum(c2s)}/{len(c2s)}")
