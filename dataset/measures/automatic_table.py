"""Automatic (non-annotated) measures per model, for the table in FINDINGS.md.

usage (from the repository folder): python dataset/measures/automatic_table.py
Distinct names are counted on 50 random subsamples of 89 stories, so every model is measured on
the same sample size. Name origin and gender come from name lists and are coarse signals.
"""
import random
from collections import Counter

from biasprobe.analysis import build_report
from biasprobe.demographics import analyze_demographics
from biasprobe.storage import Storage

ORDER = ["claude-haiku", "claude-sonnet", "claude-opus", "claude-haiku-single", "claude-sonnet-single",
         "claude-opus-single", "gemma-4-e4b-it", "qwen3.5-4b", "qwen3.5-9b", "qwen3.5-27b",
         "mistral-7b-instruct-v0.3", "olmo-3-7b-instruct", "olmo-3.1-32b-instruct", "gpt-oss-20b"]
st = Storage("data/biasprobe.db")
report = build_report(st)["models"]
random.seed(1234)


def names_in(stories):
    out = []
    for s in stories:
        out.append({c.name for c in analyze_demographics(s["text"]).characters})
    return out


rows = {}
for m in ORDER:
    stories = st.list_stories(model=m)
    if not stories:
        continue
    r = report[m]
    per_story = names_in(stories)
    k = min(89, len(per_story))
    distinct = sum(len(set().union(*random.sample(per_story, k))) for _ in range(50)) / 50
    df = Counter(n for names in per_story for n in names)
    top, top_n = df.most_common(1)[0]
    p = r["patterns"]
    rows[m] = {
        "stories / mean words": f"{r['stories']} / {r['avg_words']:.0f}",
        "protagonist male, all": f"{r['demographics_all']['protagonist_gender']['male']:.0%}",
        "protagonist male, cue-free": f"{r['demographics_default']['protagonist_gender']['male']:.0%}",
        "protagonist Anglo/Western": f"{r['demographics_all']['protagonist_origin']['anglo_western']:.0%}",
        "stories with a non-Western name": f"{r['demographics_all']['share_stories_with_non_western_name']:.0%}",
        f"distinct names per {k} stories": f"{distinct:.0f}",
        "most reused name": f"{top} {top_n / len(stories):.0%}",
        "protagonist origin unknown": f"{r['demographics_all']['protagonist_origin']['unknown']:.0%}",
        "gender cues that are male": f"{p['male_share']:.0%}",
        "stereotypical share of gender+job pairs": f"{p['gender_role_stereo_share']:.0%}",
    }
measures = list(next(iter(rows.values())))
print("| measure | " + " | ".join(rows) + " |\n|---|" + "---|" * len(rows))
for key in measures:
    print(f"| {key} | " + " | ".join(rows[m][key] for m in rows) + " |")
