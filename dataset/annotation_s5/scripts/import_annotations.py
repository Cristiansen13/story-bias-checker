"""Validate and store the balanced round; print rates, agreement and family comparisons.

usage (from the repository folder):
    PYTHONPATH=. python dataset/annotation_s5/scripts/import_annotations.py [--store]
Targets are stored as annotator-s5-partNN with the v2.1 protocol's notes and spans; repeats are
scored for agreement and not stored. A label counts as casting if the annotator's `casting` list
names it; a story is "beyond casting" if it has a label that is not casting.
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS

ROOT = Path(__file__).resolve().parents[1]
store = "--store" in sys.argv
mapping = json.loads((ROOT / "mapping.json").read_text("utf-8"))
st = Storage("data/biasprobe.db")
QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", "…": "..."})
ORDERED = ["claude-haiku-single", "claude-sonnet-single", "claude-opus-single", "gemma-4-e4b-it", "qwen3.5-4b",
           "qwen3.5-9b", "qwen3.5-27b", "mistral-7b-instruct-v0.3", "olmo-3-7b-instruct",
           "olmo-3.1-32b-instruct", "gpt-oss-20b"]
FAMILIES = {"Claude": ORDERED[:3], "Gemma": ORDERED[3:4], "Qwen3.5": ORDERED[4:7], "Mistral": ORDERED[7:8],
            "OLMo": ORDERED[8:10], "gpt-oss": ORDERED[10:], "all open": ORDERED[3:]}


def locate(text, quote):
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    norm, idx = [], []
    for k, ch in enumerate(text):
        t = ch.translate(QUOTES)
        if t.isspace():
            if norm and norm[-1] == " ":
                continue
            t = " "
        for c in t:
            norm.append(c)
            idx.append(k)
    ntext, nq = "".join(norm), re.sub(r"\s+", " ", quote.translate(QUOTES)).strip()
    j = ntext.find(nq)
    if j < 0 and len(nq) > 30:
        nq = nq[:30]
        j = ntext.find(nq)
    return None if j < 0 else (idx[j], idx[j + len(nq) - 1] + 1)


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{p:.0%} ({c - h:.0%}–{c + h:.0%})"


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def z_test(k1, n1, k2, n2):
    p = (k1 + k2) / (n1 + n2)
    return (k1 / n1 - k2 / n2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))


problems = Counter()


def parts(rec):
    """(all labels, casting labels, labels that are more than casting)"""
    labels = [x for x in rec.get("labels", []) if x in LABEL_KEYS]
    casting = {c.get("label") for c in rec.get("casting", [])} & set(labels)
    return set(labels), casting, set(labels) - casting


results = {}
for f in sorted((ROOT / "results").glob("batch_*.json")):
    for rec in json.loads(f.read_text("utf-8")):
        if rec.get("id") not in mapping:
            problems["unknown id"] += 1
            continue
        results[rec["id"]] = rec
        problems["invalid label"] += sum(x not in LABEL_KEYS for x in rec.get("labels", []))
missing = sorted(set(mapping) - set(results))
print(f"{len(results)} results of {len(mapping)}; missing {len(missing)}: {missing[:12]}")

by_story = defaultdict(dict)
already = {a["story_id"] for a in
           st._fetchall("SELECT story_id FROM annotations WHERE annotator LIKE 'annotator-s5-%'")}
stored = quotes = found = 0
for anon, rec in results.items():
    it = mapping[anon]
    by_story[it["story_id"]][it["role"]] = rec
    by_story[it["story_id"]]["item"] = it
    text = st.get_story(it["story_id"])["text"]
    labels = parts(rec)[0]
    spans = []
    for lab, q in (rec.get("evidence") or {}).items():
        quotes += 1
        loc = locate(text, q) if isinstance(q, str) else None
        if loc:
            found += 1
            spans.append({"start": loc[0], "end": loc[1], "label": lab})
    if store and it["role"] == "target" and it["story_id"] not in already:
        st.add_annotation(it["story_id"], sorted(labels), spans=spans, notes=rec.get("notes", ""),
                          annotator=f"annotator-s5-part{it['batch']:02d}", kind="agent")
        stored += 1
print(f"quotes located: {found}/{quotes}; problems {dict(problems)}; stored {stored}")

rows = defaultdict(Counter)
for roles in by_story.values():
    if "target" not in roles:
        continue
    labels, casting, beyond = parts(roles["target"])
    r = rows[roles["item"]["model"]]
    r["n"] += 1
    r["any"] += bool(labels)
    r["beyond"] += bool(beyond)
    r["casting_only"] += bool(labels) and not beyond
    for lab in labels:
        r[lab] += 1

print("\n| model | any label | beyond casting | casting only | gender roles | gender traits | racial/ethnic "
      "| nationality | age | occupation | labels/story |\n|---|---|---|---|---|---|---|---|---|---|---|")
for m in ORDERED:
    r = rows[m]
    if r["n"]:
        n = r["n"]
        total = sum(r[k] for k in LABEL_KEYS)
        print(f"| {m} | {wilson(r['any'], n)} | {wilson(r['beyond'], n)} | {r['casting_only'] / n:.0%} "
              f"| {r['gender_role'] / n:.0%} | {r['gender_trait'] / n:.0%} | {r['racial_ethnic'] / n:.0%} "
              f"| {r['xenophobia'] / n:.0%} | {r['age'] / n:.0%} | {r['profession'] / n:.0%} | {total / n:.2f} |")


def family(names):
    k = Counter()
    for m in names:
        for x in ("n", "any", "beyond", "gender_role", "racial_ethnic", "xenophobia"):
            k[x] += rows[m][x]
    return k


print("\n| family | stories | any label | beyond casting | gender roles | racial/ethnic | nationality |"
      "\n|---|---|---|---|---|---|---|")
for name, ms in FAMILIES.items():
    k = family(ms)
    if k["n"]:
        print(f"| {name} | {k['n']} | {wilson(k['any'], k['n'])} | {wilson(k['beyond'], k['n'])} "
              f"| {k['gender_role'] / k['n']:.0%} | {k['racial_ethnic'] / k['n']:.0%} | {k['xenophobia'] / k['n']:.0%} |")
c, o = family(FAMILIES["Claude"]), family(FAMILIES["all open"])
if c["n"] and o["n"]:
    print(f"open minus Claude: any {o['any'] / o['n'] - c['any'] / c['n']:+.1%} "
          f"(z {z_test(o['any'], o['n'], c['any'], c['n']):.1f}), "
          f"beyond {o['beyond'] / o['n'] - c['beyond'] / c['n']:+.1%} "
          f"(z {z_test(o['beyond'], o['n'], c['beyond'], c['n']):.1f})")

pairs = [v for v in by_story.values() if "target" in v and "repeat" in v]
if pairs:
    print(f"\nrepeats scored: {len(pairs)}")
    for name, fn in (("any label", lambda r: bool(parts(r)[0])), ("any casting", lambda r: bool(parts(r)[1])),
                     ("beyond casting", lambda r: bool(parts(r)[2]))):
        a, b = [fn(p["target"]) for p in pairs], [fn(p["repeat"]) for p in pairs]
        print(f"  {name}: agree {sum(x == y for x, y in zip(a, b))}/{len(a)}, kappa {kappa(a, b):.2f}")
    same = sum(parts(p["target"])[0] == parts(p["repeat"])[0] for p in pairs)
    print(f"  identical label set: {same}/{len(pairs)}")

shared = {"gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"}
a, b = [], []
for sid, roles in by_story.items():
    if roles["item"]["model"] in shared and "target" in roles:
        old = [x for x in st.annotations_for(sid) if x["annotator"].startswith("annotator-s2-")]
        if old:
            a.append(bool(old[-1]["labels"]))
            b.append(bool(parts(roles["target"])[0]))
if a:
    print(f"\nround 2 vs this round on {len(a)} shared open-model stories: labelled {sum(a)} vs {sum(b)}; "
          f"agree {sum(x == y for x, y in zip(a, b))}/{len(a)}, kappa {kappa(a, b):.2f}")

batches = defaultdict(lambda: [0, 0])
for anon, rec in results.items():
    batches[mapping[anon]["batch"]][0] += bool(rec.get("labels"))
    batches[mapping[anon]["batch"]][1] += 1
if batches:
    share = [k / n for k, n in batches.values()]
    print(f"labelled share per batch: {min(share):.0%}–{max(share):.0%}")
