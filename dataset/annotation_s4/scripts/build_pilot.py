"""Build the pilot for the draft casting rule: every story rounds 1-3 labelled differently, plus 20
stories they agreed on, annotated by two independent blind groups (A and B), each in two batches
with its own shuffle.

usage (from the project folder): PYTHONPATH=. python dataset/annotation_s4/scripts/build_pilot.py OUT_DIR
OUT_DIR gets mapping.json (keep it away from the annotators) and annotator/ (what they may read).
"""
import json
import random
import re
import sys
from pathlib import Path

from biasprobe.storage import Storage

ROOT = Path("dataset")
out = Path(sys.argv[1])
st = Storage("data/biasprobe.db")


def load(d):
    res = {r["id"]: r for f in (ROOT / d / "results").glob("*.json") for r in json.loads(f.read_text("utf-8"))}
    return res, json.loads((ROOT / d / "mapping.json").read_text("utf-8"))


def casting(notes):
    return notes.lower().startswith("casting only")


res2, map2 = load("annotation_s2")
res3, map3 = load("annotation_s3")
disputed, agreed = {}, {"claude": {True: [], False: []}, "open": {True: [], False: []}}
for t, v in map3.items():
    anns = st.annotations_for(v["story_id"])
    if v["role"] == "target":
        prev = [a for a in anns if not a["annotator"].startswith("annotator-s3-")][-1]; fam = "claude"
    else:
        prev = [a for a in anns if a["annotator"].startswith("annotator-s2-")][-1]; fam = "open"
    if set(prev["labels"]) != set(res3[t]["labels"]):
        disputed[v["story_id"]] = v["model"]
    else:
        both_cast = casting(prev["notes"]) and casting(res3[t]["notes"])
        agreed[fam][bool(prev["labels"])].append((both_cast, v["story_id"], v["model"], sorted(prev["labels"])))
for t, v in map2.items():
    if v["role"] == "anchor":
        prev = [a for a in st.annotations_for(v["story_id"])
                if a["annotator"].startswith(("annotator-part", "annotator-re"))][-1]
        if set(prev["labels"]) != set(res2[t]["labels"]):
            disputed[v["story_id"]] = v["model"]
print(f"{len(disputed)} distinct disputed stories")

rng = random.Random(20261025)
chosen = []
for fam in ("claude", "open"):
    for labelled in (True, False):
        pool = [x for x in agreed[fam][labelled] if x[1] not in disputed]
        rng.shuffle(pool)
        if labelled:  # prefer stories both rounds called casting only, so the rule is tested on them
            pool.sort(key=lambda x: not x[0])
            pick = pool[:3] + rng.sample(pool[3:], 2)
        else:
            pick = pool[:5]
        chosen += [(sid, model, labels, cast) for cast, sid, model, labels in pick]

items = [{"story_id": sid, "model": m, "set": "disputed"} for sid, m in disputed.items()]
items += [{"story_id": sid, "model": m, "set": "agreed", "agreed_labels": labels, "agreed_casting": cast}
          for sid, m, labels, cast in chosen]
rng.shuffle(items)
mapping = {f"P{i:03d}": it for i, it in enumerate(items, 1)}
ids = list(mapping)

ann = out / "annotator"
(ann / "batches").mkdir(parents=True, exist_ok=True)
(ann / "results").mkdir(exist_ok=True)
for group in ("A", "B"):
    order = ids[:]
    random.Random(f"pilot-{group}").shuffle(order)
    half = -(-len(order) // 2)
    for b, chunk in enumerate((order[:half], order[half:]), 1):
        text = "\n\n".join(f"=== STORY {sid} ===\n{st.get_story(mapping[sid]['story_id'])['text'].strip()}"
                           for sid in chunk)
        (ann / "batches" / f"batch_{group}{b}.md").write_text(text + "\n", encoding="utf-8")
        print(f"batch_{group}{b}: {len(chunk)} stories")
(out / "mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")

# annotators get the protocol without the review banner (it points to the decisions sheet)
proto = (out / "protocol_draft.md").read_text(encoding="utf-8")
proto = re.sub(r"^# Annotation protocol \(draft v[\d.]+: explicit casting criteria\)\n\n(>.*\n)+\n",
               "# Annotation protocol\n\n", proto)
assert "casting_rule_check" not in proto and "Draft for review" not in proto
(ann / "protocol.md").write_text(proto, encoding="utf-8")
(ann / "taxonomy.md").write_text((ROOT / "annotation_s3" / "taxonomy.md").read_text("utf-8"), encoding="utf-8")
print(f"{len(ids)} stories: {sum(v['set'] == 'disputed' for v in mapping.values())} disputed, "
      f"{sum(v['set'] == 'agreed' for v in mapping.values())} agreed")
