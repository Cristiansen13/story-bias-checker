"""How well the LLM judge's scores match the annotators' latest labels.

usage (from the repository folder): python dataset/judge_outputs/agreement.py [JUDGE_NAME]
Per label: positives among annotated stories, ROC AUC of the judge's score, and F1 at the best
threshold (optimistic: the threshold is picked on the same stories). Demo stories are left out,
and a label counts only for annotations whose taxonomy offered it.
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score, roc_auc_score

from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS

judge = sys.argv[1] if len(sys.argv) > 1 else "phi-4"
st = Storage("data/biasprobe.db")
scores = st.judge_scores(judge)
latest = st.latest_annotations()
stories = {s["id"]: s for s in st.list_stories() if s["source"] != "demo"}
ids = [i for i in stories if i in latest and i in scores]
print(f"{judge}: {len(scores)} stories scored, {len(ids)} of them annotated (no demo)")

raw = st._fetchall("SELECT story_id, raw FROM judge_scores WHERE judge_model = ?", (judge,))
all_zero = sum(1 for v in scores.values() if max(v.values()) == 0)
print(f"all-zero outputs: {all_zero}/{len(scores)}; mean labels scored >= 0.5 per story: "
      f"{np.mean([sum(x >= 0.5 for x in v.values()) for v in scores.values()]):.2f}")


def best_f1(y, s):
    grid = sorted(set(np.round(s, 2))) or [0.5]
    f1s = [(f1_score(y, s >= t, zero_division=0), t) for t in grid]
    return max(f1s)


def within_premise_auc(use, y, s):
    """AUC over pairs of stories from the same premise, so that spotting the topic earns nothing."""
    groups = {}
    for i, yi, si in zip(use, y, s):
        groups.setdefault(stories[i]["probe_id"], []).append((yi, si))
    wins = pairs = 0.0
    for g in groups.values():
        for a in (si for yi, si in g if yi):
            for b in (si for yi, si in g if not yi):
                wins += (a > b) + 0.5 * (a == b)
                pairs += 1
    return wins / pairs if pairs else float("nan")


print("\n| label | positives | AUC | AUC within premise | best F1 | at score >= |\n|---|---|---|---|---|---|")
aucs = []
within = []
for key in LABEL_KEYS:
    use = [i for i in ids if key in (latest[i].get("taxonomy") or LABEL_KEYS)]
    y = np.array([key in latest[i]["labels"] for i in use])
    s = np.array([scores[i].get(key, 0.0) for i in use])
    if y.sum() < 5:
        print(f"| {key} | {y.sum()} | | | | |")
        continue
    auc = roc_auc_score(y, s)
    aucs.append(auc)
    inside = within_premise_auc(use, y, s)
    within.append(inside)
    f1, t = best_f1(y, s)
    print(f"| {key} | {y.sum()} | {auc:.2f} | {inside:.2f} | {f1:.2f} | {t:.2f} |")
print(f"mean over labels with 5+ positives: AUC {np.mean(aucs):.2f}, within premise {np.nanmean(within):.2f}")

y = np.array([bool(latest[i]["labels"]) for i in ids])
s = np.array([max(scores[i].values()) for i in ids])
f1, t = best_f1(y, s)
print(f"\nany label vs none: positives {y.sum()}/{len(ids)}, AUC {roc_auc_score(y, s):.2f} (max score), "
      f"best F1 {f1:.2f} at >= {t:.2f}, accuracy there {np.mean((s >= t) == y):.2f}")
s5_root = Path(__file__).resolve().parents[1] / "annotation_s5"
mapping = json.loads((s5_root / "mapping.json").read_text("utf-8"))
s5_casting_only = {}
for f in (s5_root / "results").glob("batch_*.json"):
    for r in json.loads(f.read_text("utf-8")):
        if mapping[r["id"]]["role"] == "target":
            labels = set(r["labels"])
            s5_casting_only[mapping[r["id"]]["story_id"]] = bool(labels) and labels <= {
                c.get("label") for c in r.get("casting", [])}
casting = np.array([s5_casting_only[i] if i in s5_casting_only else
                    bool(latest[i]["labels"]) and latest[i]["notes"].lower().startswith("casting only") for i in ids])
beyond = y & ~casting
print(f"mean max score: no label {s[~y].mean():.2f}, casting only {s[casting].mean():.2f}, beyond casting {s[beyond].mean():.2f}")
print("AUC beyond-casting vs no label: "
      f"{roc_auc_score(beyond[beyond | ~y], s[beyond | ~y]):.2f}; casting-only vs no label: "
      f"{roc_auc_score(casting[casting | ~y], s[casting | ~y]):.2f}")

s5 = [i for i in ids if latest[i]["annotator"].startswith("annotator-s5-")]
y5 = np.array([bool(latest[i]["labels"]) for i in s5])
s5_scores = np.array([max(scores[i].values()) for i in s5])
print(f"balanced round only: positives {y5.sum()}/{len(s5)}, AUC any vs none {roc_auc_score(y5, s5_scores):.2f}, "
      f"within premise {within_premise_auc(s5, y5, s5_scores):.2f}")

print("\nshare of stories with any judge score >= 0.5, by model (annotated or not):")
by = {}
for i, v in scores.items():
    if i in stories:
        by.setdefault(stories[i]["model"], []).append(max(v.values()) >= 0.5)
for m, v in sorted(by.items()):
    print(f"  {m}: {np.mean(v):.0%} of {len(v)}")
