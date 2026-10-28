"""Validate round-3 annotator output, store target annotations, score anchors and round drift.

usage: python import_annotations.py ANNOT_DIR [--store]   (run from the project folder)
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

ROUND = "s3"
already = {a["story_id"] for a in st._fetchall(f"SELECT story_id FROM annotations WHERE annotator LIKE 'annotator-{ROUND}-%'")}


def previous(story_id):
    """Latest annotation of the story from an earlier round (anchors: round 2; targets: study 1)."""
    rows = [a for a in st.annotations_for(story_id) if not a["annotator"].startswith(f"annotator-{ROUND}-")]
    return rows[-1] if rows else None


target_rows = []
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
        prev = previous(info["story_id"])
        anchor_rows.append((info["model"], set(prev["labels"]), set(labels)))
        continue
    prev = previous(info["story_id"])
    if prev:
        target_rows.append((info["model"], set(prev["labels"]), set(labels)))
    if store and info["story_id"] not in already:
        st.add_annotation(info["story_id"], labels, spans=spans, notes=rec.get("notes", ""),
                          annotator=f"annotator-{ROUND}-part{batch}", kind="agent", taxonomy=LABEL_KEYS)
        stored += 1
print("checks:", dict(problems))
print(f"stored {stored} annotations" if store else "dry run (nothing stored)")


def kappa(xs, ys):
    n = len(xs); po = sum(x == y for x, y in zip(xs, ys)) / n
    px, py = sum(xs) / n, sum(ys) / n
    pe = px * py + (1 - px) * (1 - py)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def compare(rows, title, before, now):
    n = len(rows)
    if not n:
        return
    any_agree = sum(bool(a) == bool(b) for _, a, b in rows)
    exact = sum(a == b for _, a, b in rows)
    k = kappa([bool(a) for _, a, _ in rows], [bool(b) for _, _, b in rows])
    print(f"{title}: {n}; any-vs-none agreement {any_agree}/{n} (kappa {k:.2f}); identical label set {exact}/{n}")
    print(f"  {before} any-bias", sum(bool(a) for _, a, _ in rows), "/", n,
          f"| {now}", sum(bool(b) for _, _, b in rows), "/", n)
    a_only = sum(bool(a) and not b for _, a, b in rows); b_only = sum(bool(b) and not a for _, a, b in rows)
    print(f"  labelled only by {before}: {a_only}; only by {now}: {b_only}")
    for label in LABEL_KEYS:
        a = sum(label in x for _, x, _ in rows); b = sum(label in y for _, _, y in rows)
        both = sum(label in x and label in y for _, x, y in rows)
        if a or b:
            kl = kappa([label in x for _, x, _ in rows], [label in y for _, _, y in rows])
            print(f"  {label:<14} {before} {a:>3}  {now} {b:>3}  both {both:>3}  kappa {kl:.2f}")


compare(anchor_rows, "anchors (open models, round 2 vs round 3)", "round2", "round3")
compare(target_rows, "Claude targets (study 1 vs round 3)", "study1", "round3")
