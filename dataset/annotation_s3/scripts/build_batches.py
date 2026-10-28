"""Build blind batches for round 3: Claude's one-per-probe stories re-annotated, with hidden
round-2 open-model stories as anchors (5 labelled + 5 clean per model)."""
import json, random, sys
from pathlib import Path
from biasprobe.storage import Storage

out = Path(sys.argv[1]); n_batches = int(sys.argv[2])
st = Storage("data/biasprobe.db")
targets = []
for m in ["claude-haiku", "claude-sonnet", "claude-opus"]:
    first = {}
    for s in sorted(st.list_stories(model=m), key=lambda s: s["id"]):
        first.setdefault(s["probe_id"], s)
    targets += first.values()
assert len(targets) == 267, len(targets)
s2 = {a["story_id"]: a for a in st._fetchall(
    "SELECT story_id, labels FROM annotations WHERE annotator LIKE 'annotator-s2-%'")}
rng = random.Random(20261024)
anchors = []
for m in ["gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"]:
    pool = [s for s in st.list_stories(model=m) if s["id"] in s2]
    labelled = [s for s in pool if s2[s["id"]]["labels"]]
    clean = [s for s in pool if not s2[s["id"]]["labels"]]
    anchors += rng.sample(labelled, 5) + rng.sample(clean, 5)
items = [("target", s) for s in targets] + [("anchor", s) for s in anchors]
rng.shuffle(items)
mapping = {f"R{i:03d}": {"story_id": s["id"], "role": role, "model": s["model"]}
           for i, (role, s) in enumerate(items, 1)}
ids = list(mapping)
size = -(-len(ids) // n_batches)
for b in range(n_batches):
    chunk = ids[b * size:(b + 1) * size]
    text = "\n\n".join(f"=== STORY {sid} ===\n{st.get_story(mapping[sid]['story_id'])['text'].strip()}"
                       for sid in chunk)
    (out / "batches" / f"batch_{b + 1}.md").write_text(text + "\n", encoding="utf-8")
    print(f"batch_{b + 1}: {len(chunk)} stories ({chunk[0]}..{chunk[-1]})")
(out / "mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")
print(len(ids), "stories;", sum(v["role"] == "anchor" for v in mapping.values()), "anchors")
