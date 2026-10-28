"""Human-perceived bias rates for study 2 vs study 1."""
import math
from collections import Counter, defaultdict
from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS

st = Storage("data/biasprobe.db")
latest = st.latest_annotations()
claude = ["claude-haiku", "claude-sonnet", "claude-opus"]
new = ["gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b"]


def wilson(k, n, z=1.96):
    if not n:
        return 0, 0
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sets():
    out = {}
    for m in claude:
        stories = st.list_stories(model=m)
        out[m + " (all)"] = [s for s in stories if s["id"] in latest]
        first = {}
        for s in sorted(stories, key=lambda s: s["id"]):
            first.setdefault(s["probe_id"], s)
        out[m] = [s for s in first.values() if s["id"] in latest]
    for m in new:
        out[m] = [s for s in st.list_stories(model=m) if s["id"] in latest]
    return out


S = sets()
cols = claude + [m + " (all)" for m in claude] + new
print("| measure | " + " | ".join(cols) + " |")
rows = defaultdict(list)
for m in cols:
    ss = S[m]; n = len(ss)
    labs = [set(latest[s["id"]]["labels"]) for s in ss]
    k = sum(bool(l) for l in labs); lo, hi = wilson(k, n)
    rows["n"].append(str(n))
    rows["any"].append(f"{100*k/n:.0f}% ({100*lo:.0f}–{100*hi:.0f})")
    cast = sum(bool(l) and latest[s['id']]["notes"].lower().startswith("casting only") for s, l in zip(ss, labs))
    rows["casting-only share of labelled"].append(f"{100*cast/max(1,k):.0f}%")
    rows["labels per story"].append(f"{sum(len(l) for l in labs)/n:.2f}")
    for lab in LABEL_KEYS:
        rows[lab].append(f"{100*sum(lab in l for l in labs)/n:.0f}%")
for key, vals in rows.items():
    if key in LABEL_KEYS and all(v == "0%" for v in vals):
        continue
    print(f"| {key} | " + " | ".join(vals) + " |")

# pooled groups on the matched probe set
for name, group in (("claude (3, one per probe)", claude), ("open (4)", new), ("qwen (3)", new[1:])):
    labs = [set(latest[s["id"]]["labels"]) for m in group for s in S[m]]
    k = sum(bool(l) for l in labs); lo, hi = wilson(k, len(labs))
    print(f"{name}: {k}/{len(labs)} = {100*k/len(labs):.0f}% ({100*lo:.0f}–{100*hi:.0f}); gender_role "
          f"{100*sum('gender_role' in l for l in labs)/len(labs):.0f}%; racial_ethnic {100*sum('racial_ethnic' in l for l in labs)/len(labs):.0f}%")

# by probe category, pooled open models vs pooled claude (matched)
print()
cat = defaultdict(lambda: {"c": [0, 0], "o": [0, 0]})
for grp, ms in (("c", claude), ("o", new)):
    for m in ms:
        for s in S[m]:
            c = cat[s["probe_category"]][grp]; c[0] += 1; c[1] += bool(latest[s["id"]]["labels"])
print("| category | claude (3) | open models (4) |")
for k, v in sorted(cat.items(), key=lambda kv: -kv[1]["o"][1] / max(1, kv[1]["o"][0])):
    print(f"| {k} | {v['c'][1]}/{v['c'][0]} | {v['o'][1]}/{v['o'][0]} = {100*v['o'][1]/max(1,v['o'][0]):.0f}% |")

# probes labelled for all four open models
print()
hits = defaultdict(list)
for m in new:
    for s in S[m]:
        hits[s["probe_id"]].append((m, latest[s["id"]]["labels"]))
allfour = [(p, v) for p, v in hits.items() if all(l for _, l in v)]
print("probes labelled for all 4 open models:", len(allfour))
for p, v in sorted(allfour):
    print(f"  {p}: " + "; ".join(f"{m.split('-')[0] if 'gemma' in m else m.replace('qwen3.5-','q')}={','.join(l)}" for m, l in v))
three = [p for p, v in hits.items() if sum(bool(l) for _, l in v) == 3]
print("labelled for exactly 3 of 4:", sorted(three))
