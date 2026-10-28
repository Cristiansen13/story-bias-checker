"""Validate study-2 annotator output, store target annotations, score the hidden anchors.

usage: python import_annotations.py ANNOT_DIR [--store]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS

root = Path(sys.argv[1]); store = "--store" in sys.argv
mapping = json.loads((root / "mapping.json").read_text(encoding="utf-8"))
st = Storage("data/biasprobe.db")

QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", "…": "..."})


def locate(text: str, quote: str) -> tuple[int, int] | None:
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    # tolerate quote-style / dash / whitespace differences; map back to original offsets
    norm, idx = [], []
    for k, ch in enumerate(text):
        t = ch.translate(QUOTES)
        if t.isspace():
            if norm and norm[-1] == " ":
                continue
            t = " "
        for c in t:
            norm.append(c); idx.append(k)
    ntext = "".join(norm)
    nq = re.sub(r"\s+", " ", quote.translate(QUOTES)).strip()
    j = ntext.find(nq)
    if j < 0 and len(nq) > 30:  # last resort: the first 30 characters
        j = ntext.find(nq[:30]); nq = nq[:30] if j >= 0 else nq
    if j < 0:
        return None
    return idx[j], idx[j + len(nq) - 1] + 1


results, problems = {}, Counter()
for f in sorted((root / "results").glob("batch_*.json")):
    batch = int(re.search(r"(\d+)", f.stem).group(1))
    for rec in json.loads(f.read_text(encoding="utf-8")):
        results[rec["id"]] = (batch, rec)
missing = sorted(set(mapping) - set(results))
print(f"{len(results)} results, {len(missing)} missing: {missing[:10]}")

already = {a["story_id"] for a in st._fetchall("SELECT story_id FROM annotations WHERE annotator LIKE 'annotator-s2-%'")}
stored = 0
anchor_rows = []
for sid, (batch, rec) in sorted(results.items()):
    info = mapping.get(sid)
    if info is None:
        problems["unknown id"] += 1
        continue
    story = st.get_story(info["story_id"])
    labels = [l for l in rec.get("labels", []) if l in LABEL_KEYS]
    problems["invalid label"] += len(rec.get("labels", [])) - len(labels)
    spans = []
    for label in labels:
        quote = (rec.get("evidence") or {}).get(label)
        loc = locate(story["text"], quote) if quote else None
        if loc is None:
            problems["quote not found" if quote else "no quote"] += 1
            continue
        spans.append({"start": loc[0], "end": loc[1], "label": label})
    problems["labels"] += len(labels); problems["spans"] += len(spans)
    if info["role"] == "anchor":
        prev = st.latest_annotation(info["story_id"])
        anchor_rows.append((info["model"], set(prev["labels"]), set(labels)))
        continue
    if store and info["story_id"] not in already:
        st.add_annotation(info["story_id"], labels, spans=spans, notes=rec.get("notes", ""),
                          annotator=f"annotator-s2-part{batch}", kind="agent", taxonomy=LABEL_KEYS)
        stored += 1
print("checks:", dict(problems))
print(f"stored {stored} annotations" if store else "dry run (nothing stored)")

# --- drift check against study 1 on the hidden anchors
n = len(anchor_rows)
if n:
    any_agree = sum(bool(a) == bool(b) for _, a, b in anchor_rows)
    exact = sum(a == b for _, a, b in anchor_rows)
    print(f"anchors: {n}; any-vs-none agreement {any_agree}/{n}; identical label set {exact}/{n}")
    print("  study-1 any-bias rate", sum(bool(a) for _, a, _ in anchor_rows), "/", n,
          "| this round", sum(bool(b) for _, _, b in anchor_rows), "/", n)
    for label in LABEL_KEYS:
        a = sum(label in x for _, x, _ in anchor_rows); b = sum(label in y for _, _, y in anchor_rows)
        both = sum(label in x and label in y for _, x, y in anchor_rows)
        if a or b:
            print(f"  {label:<14} study1 {a:>2}  now {b:>2}  both {both:>2}")
