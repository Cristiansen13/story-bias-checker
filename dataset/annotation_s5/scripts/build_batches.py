"""Build the balanced annotation round: every batch holds the same mix of all models.

usage (from the repository folder): PYTHONPATH=. python dataset/annotation_s5/scripts/build_batches.py
Writes batches/, protocol.md, taxonomy.md and mapping.json next to this folder. One story per
premise and model (the first sample that exists); Claude is represented by its one-call stories.
A story's batch is (premise + 2 * model) mod 22, so a batch never repeats a premise and holds 4 or
5 stories per model. 44 stories (4 per model) appear again in another batch under a new id, to
measure agreement within the round; those repeats are scored, not stored.
"""
import json
import random
import re
from collections import Counter
from pathlib import Path

from biasprobe.storage import Storage

MODELS = ["claude-haiku-single", "claude-sonnet-single", "claude-opus-single", "gemma-4-e4b-it", "qwen3.5-4b",
          "qwen3.5-9b", "qwen3.5-27b", "mistral-7b-instruct-v0.3", "olmo-3-7b-instruct", "olmo-3.1-32b-instruct",
          "gpt-oss-20b"]
N_BATCHES, N_REPEATS = 22, 4
ROOT = Path(__file__).resolve().parents[1]
rng = random.Random("annotation-s5")
st = Storage("data/biasprobe.db")

premises = sorted({s["probe_id"] for s in st.list_stories(model=MODELS[0])})
assert len(premises) == 89
picked = {}
for j, model in enumerate(MODELS):
    by_probe = {}
    for s in st.list_stories(model=model):
        by_probe.setdefault(s["probe_id"], []).append(s)
    for i, probe in enumerate(premises):
        s = min(by_probe[probe], key=lambda x: x["meta"].get("sample_index", 0))
        picked[(i, j)] = s
batches = {b: [] for b in range(N_BATCHES)}
for (i, j), s in picked.items():
    batches[(i + 2 * j) % N_BATCHES].append({"story_id": s["id"], "model": MODELS[j], "probe_id": s["probe_id"],
                                             "sample_index": s["meta"].get("sample_index", 0), "role": "target"})
# repeats: 4 stories per model, each into a batch that does not hold its premise, 2 per batch
slots = [b for b in range(N_BATCHES) for _ in range(2)]
rng.shuffle(slots)
repeats = []
for j, model in enumerate(MODELS):  # a premise only sits in batches of one parity, so balance the parities
    for parity in (0, 1):
        repeats += rng.sample([key for key in picked if key[1] == j and key[0] % 2 == parity], N_REPEATS // 2)
rng.shuffle(repeats)
repeat_of = {}
for key in repeats:
    s = picked[key]
    home = (key[0] + 2 * key[1]) % N_BATCHES
    b = next(x for x in slots if x != home and all(it["probe_id"] != s["probe_id"] for it in batches[x]))
    slots.remove(b)
    batches[b].append({"story_id": s["id"], "model": MODELS[key[1]], "probe_id": s["probe_id"],
                       "sample_index": s["meta"].get("sample_index", 0), "role": "repeat"})
ids = [f"V{i:04d}" for i in range(1, 2000)]
rng.shuffle(ids)
ids = iter(ids)
mapping = {}
(ROOT / "batches").mkdir(exist_ok=True)
for b, items in batches.items():
    rng.shuffle(items)
    blocks = []
    for it in items:
        anon = next(ids)
        mapping[anon] = {**it, "batch": b + 1}
        blocks.append(f"=== STORY {anon} ===\n{st.get_story(it['story_id'])['text'].strip()}")
    (ROOT / "batches" / f"batch_{b + 1:02d}.md").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    assert len({it["probe_id"] for it in items}) == len(items)
    mix = Counter(it["model"] for it in items if it["role"] == "target")
    assert set(mix.values()) <= {4, 5} and len(mix) == len(MODELS), mix
(ROOT / "mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")

docs = ROOT.parents[1] / "docs" / "annotation"
proto = (docs / "protocol_v2.1.md").read_text("utf-8")
proto, n = re.subn(r"^# Annotation protocol \(draft v[\d.]+: explicit casting criteria\)\n\n(>.*\n)+\n",
                   "# Annotation protocol\n\n", proto)
assert n == 1 and "dataset/" not in proto and "round-4" not in proto and "Draft" not in proto
(ROOT / "protocol.md").write_text(proto, encoding="utf-8")
(ROOT / "taxonomy.md").write_text((docs / "taxonomy.md").read_text("utf-8"), encoding="utf-8")
sizes = [len(v) for v in batches.values()]
print(f"{len(picked)} targets + {len(repeats)} repeats in {N_BATCHES} batches of {min(sizes)}-{max(sizes)}")
print("not first sample:", [(it["model"], it["probe_id"], it["sample_index"]) for v in batches.values() for it in v
                            if it["sample_index"] not in (0, None) and it["role"] == "target"])
