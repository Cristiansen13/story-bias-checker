"""Build blind annotation batches for study 2 (plus hidden study-1 anchors)."""
import json, random, sys
from pathlib import Path
from biasprobe.storage import Storage
from biasprobe.taxonomy import LABELS

out = Path(sys.argv[1]); n_batches = int(sys.argv[2])
st = Storage("data/biasprobe.db")
new_models = ["gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"]
targets = [s for m in new_models for s in st.list_stories(model=m) if s["meta"].get("sample_index") == 0]
assert len(targets) == 356, len(targets)
latest = st.latest_annotations()
rng = random.Random(20261023)
anchors = []
for m in ["claude-haiku", "claude-sonnet", "claude-opus"]:
    pool = [s for s in st.list_stories(model=m)
            if s["id"] in latest and len(latest[s["id"]]["taxonomy"] or []) == len(LABELS)]
    anchors += rng.sample(pool, 10)
items = [("target", s) for s in targets] + [("anchor", s) for s in anchors]
rng.shuffle(items)
mapping = {}
for i, (role, s) in enumerate(items, 1):
    mapping[f"T{i:03d}"] = {"story_id": s["id"], "role": role, "model": s["model"]}
ids = list(mapping)
size = -(-len(ids) // n_batches)
for b in range(n_batches):
    chunk = ids[b * size:(b + 1) * size]
    text = "\n\n".join(f"=== STORY {sid} ===\n{st.get_story(mapping[sid]['story_id'])['text'].strip()}" for sid in chunk)
    (out / "batches" / f"batch_{b + 1}.md").write_text(text + "\n", encoding="utf-8")
    print(f"batch_{b + 1}: {len(chunk)} stories ({chunk[0]}..{chunk[-1]})")
(out / "private" / "mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")
tax = "\n".join(f"- `{l.key}` ({l.name}): {l.description}\n  Examples: " + " / ".join(f'"{e}"' for e in l.examples)
                for l in LABELS)
(out / "taxonomy.md").write_text(tax + "\n", encoding="utf-8")
print(len(ids), "stories;", sum(v["role"] == "anchor" for v in mapping.values()), "anchors")
