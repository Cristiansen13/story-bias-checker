"""Build the Milestone 1 project plan (PDF, A4) for the biasprobe study.

usage: python docs/milestone1/build_plan.py   ->   docs/milestone1/milestone1_plan.pdf
Needs reportlab and the Windows fonts Georgia and Segoe UI.
"""

import math
from pathlib import Path

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = Path(__file__).with_name("milestone1_plan.pdf")
FONTS = Path("C:/Windows/Fonts")
for name, file in (("Body", "georgia.ttf"), ("Body-Italic", "georgiai.ttf"), ("Body-Bold", "georgiab.ttf"),
                   ("Body-BoldItalic", "georgiaz.ttf"), ("Sans", "segoeui.ttf"), ("Sans-Bold", "segoeuib.ttf"),
                   ("Sans-Light", "segoeuisl.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
pdfmetrics.registerFontFamily("Body", normal="Body", italic="Body-Italic", bold="Body-Bold",
                              boldItalic="Body-BoldItalic")
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans", boldItalic="Sans-Bold")

INK = colors.HexColor("#1F2A37")
MUTED = colors.HexColor("#5A6675")
ACCENT = colors.HexColor("#2F5D8A")
ACCENT_SOFT = colors.HexColor("#EAF0F6")
LOOP = colors.HexColor("#B0651F")
RULE = colors.HexColor("#C9D3DE")
ANY = colors.HexColor("#2A64B0")     # results figure: any perceived stereotype
BEYOND = colors.HexColor("#C26A1E")  # results figure: stereotype beyond casting
GRID = colors.HexColor("#E3E8EE")
BAND = colors.HexColor("#F3F5F8")

BODY = ParagraphStyle("body", fontName="Body", fontSize=9.4, leading=13.1, textColor=INK,
                      alignment=TA_JUSTIFY, spaceAfter=4.5)
LEAD = ParagraphStyle("lead", parent=BODY, spaceAfter=3)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=11, bulletIndent=1, spaceAfter=2.6)
H1 = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=11.6, leading=14, textColor=ACCENT,
                    spaceBefore=8.5, spaceAfter=3.5, keepWithNext=1)
TITLE = ParagraphStyle("title", fontName="Sans-Bold", fontSize=18, leading=22, textColor=INK, spaceAfter=2)
SUBTITLE = ParagraphStyle("subtitle", fontName="Sans", fontSize=10.2, leading=13, textColor=MUTED, spaceAfter=1)
CELL = ParagraphStyle("cell", fontName="Body", fontSize=8.4, leading=10.9, textColor=INK, alignment=TA_LEFT)
CELL_HEAD = ParagraphStyle("cellhead", fontName="Sans-Bold", fontSize=8.2, leading=10.4, textColor=INK)
CAPTION = ParagraphStyle("caption", fontName="Body-Italic", fontSize=8.2, leading=10.4, textColor=MUTED,
                         spaceBefore=2, spaceAfter=5)
REF = ParagraphStyle("ref", fontName="Body", fontSize=7.7, leading=9.4, textColor=INK, leftIndent=12,
                     firstLineIndent=-12, spaceAfter=1.2, alignment=TA_LEFT)

W = A4[0] - 4.0 * cm  # text width


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items, style=BULLET):
    return [Paragraph(t, style, bulletText="•") for t in items]


def styled_table(rows, col_widths, extra=()):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        *extra,
    ]))
    return t


def wilson(k, n, z=1.96):
    """Share k/n and its 95% Wilson interval, in percent."""
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * p, 100 * (centre - half), 100 * (centre + half)


# ----------------------------------------------------------------------------------- figure

def pipeline_figure():
    d = Drawing(W, 182)
    bw, bh, gap = 142, 62, (W - 3 * 142) / 2
    top_y, bot_y = 108, 22
    xs = [0, bw + gap, 2 * (bw + gap)]

    def box(x, y, title, lines):
        d.add(Rect(x, y, bw, bh, rx=5, ry=5, fillColor=ACCENT_SOFT, strokeColor=ACCENT, strokeWidth=0.9))
        d.add(String(x + 8, y + bh - 14, title, fontName="Sans-Bold", fontSize=8.6, fillColor=INK))
        for i, line in enumerate(lines):
            d.add(String(x + 8, y + bh - 27 - i * 10.2, line, fontName="Sans", fontSize=7.1, fillColor=MUTED))

    def arrow(x1, y1, x2, y2, color=ACCENT, width=1.1):
        d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=width))
        ang = math.atan2(y2 - y1, x2 - x1)
        s = 5.2
        a = (x2 - s * math.cos(ang - 0.42), y2 - s * math.sin(ang - 0.42))
        b = (x2 - s * math.cos(ang + 0.42), y2 - s * math.sin(ang + 0.42))
        d.add(Polygon([x2, y2, a[0], a[1], b[0], b[1]], fillColor=color, strokeColor=color, strokeWidth=0.5))

    box(xs[0], top_y, "1  Probe bank", ["89 story premises, 19 categories", "gender, origin, age, roles left open",
                                         "bias is never mentioned"])
    box(xs[1], top_y, "2  Generation", ["same premises for every model", "one prompt + sampling configuration",
                                         "resumable, several samples per premise"])
    box(xs[2], top_y, "3  Clean & store", ["strip reasoning blocks and titles", "drop short outputs, deduplicate",
                                            "SQLite: stories, all annotation rounds"])
    box(xs[2], bot_y, "4  Blind annotation", ["17 labels, casting criteria C1–C4", "exact evidence quotes \u2192 spans",
                                               "mixed batches, repeated stories (\u03ba)"])
    box(xs[1], bot_y, "5  Classifier & analyzers", ["semi-supervised, per-label thresholds",
                                                     "evidence sentences, optional LLM judge",
                                                     "lexical + default-demographics analysis"])
    box(xs[0], bot_y, "6  Report", ["per-model rates with 95% intervals", "beyond-casting rate, per category",
                                     "lexical and demographic tables"])
    mid_top, mid_bot = top_y + bh / 2, bot_y + bh / 2
    arrow(xs[0] + bw, mid_top, xs[1] - 1.5, mid_top)
    arrow(xs[1] + bw, mid_top, xs[2] - 1.5, mid_top)
    arrow(xs[2] + bw / 2, top_y, xs[2] + bw / 2, bot_y + bh + 1.5)
    arrow(xs[2], mid_bot + 8, xs[1] + bw + 1.5, mid_bot + 8)
    arrow(xs[1], mid_bot, xs[0] + bw + 1.5, mid_bot)
    # human-in-the-loop: flags from the classifier go back to reviewers as new labels
    lx1, lx2, ly = xs[1] + bw * 0.7, xs[2] + bw * 0.3, bot_y - 11
    d.add(Line(lx1, bot_y, lx1, ly, strokeColor=LOOP, strokeWidth=1.1))
    d.add(Line(lx1, ly, lx2, ly, strokeColor=LOOP, strokeWidth=1.1))
    arrow(lx2, ly, lx2, bot_y - 1.5, color=LOOP)
    d.add(String((lx1 + lx2) / 2, ly - 9.5, "review loop: flags queued by uncertainty, accepted / rejected flags become labels",
                 fontName="Sans", fontSize=6.9, fillColor=LOOP, textAnchor="middle"))
    d.add(String(xs[2] - gap / 2, mid_bot + 12.5, "labels", fontName="Sans", fontSize=6.5, fillColor=ACCENT,
                 textAnchor="middle"))
    return d


# one story per premise and model, labelled blind in one balanced round:
# (model, stories with any label, stories with a stereotype beyond casting, stories)
RATES = [
    ("Claude", [("Haiku", 33, 8, 89), ("Sonnet", 26, 8, 89), ("Opus", 21, 3, 89), ("All Claude", 80, 19, 267)]),
    ("Open-weight", [("Gemma 4 E4B", 42, 21, 89), ("Qwen3.5 4B", 45, 30, 89), ("Qwen3.5 9B", 38, 21, 89),
                     ("Qwen3.5 27B", 43, 24, 89), ("Mistral 7B", 55, 44, 89), ("OLMo 3 7B", 23, 9, 89),
                     ("OLMo 3.1 32B", 34, 16, 89), ("gpt-oss 20B", 34, 19, 89), ("All open-weight", 314, 184, 712)]),
]


def results_figure():
    pitch, label_w, xmax = 11.6, 112, 80
    n_rows = sum(len(rows) + 1 for _, rows in RATES)
    h = n_rows * pitch + 34
    d = Drawing(W, h)
    x0, x1, axis_y, top = label_w, W - 22, 12, h - 24

    def x(v):
        return x0 + (x1 - x0) * v / xmax

    def marker(cx, cy, color, shape):
        if shape == "circle":
            d.add(Circle(cx, cy, 3.0, fillColor=color, strokeColor=colors.white, strokeWidth=0.8))
        else:
            r = 3.8
            d.add(Polygon([cx, cy + r, cx + r, cy, cx, cy - r, cx - r, cy], fillColor=color,
                          strokeColor=colors.white, strokeWidth=0.8))

    rows, y = [], top
    for group, models in RATES:
        rows.append((y, group, None))
        y -= pitch
        for m in models:
            rows.append((y, None, m))
            y -= pitch
    for ry, _, m in rows:
        if m and m[0].startswith("All"):
            d.add(Rect(0, ry - pitch / 2, W, pitch, fillColor=BAND, strokeColor=None))
    for v in range(0, xmax + 1, 10):
        d.add(Line(x(v), axis_y + 6, x(v), top + 6, strokeColor=GRID, strokeWidth=0.5))
        d.add(String(x(v), axis_y - 3, f"{v}%", fontName="Sans", fontSize=6.8, fillColor=MUTED,
                     textAnchor="middle"))
    for ry, group, m in rows:
        if group:
            d.add(String(0, ry - 2.5, group, fontName="Sans-Bold", fontSize=7.4, fillColor=INK))
            continue
        name, k_any, k_beyond, n = m
        pooled = name.startswith("All")
        d.add(String(9, ry - 2.5, f"{name} ({n})" if pooled else name,
                     fontName="Sans-Bold" if pooled else "Sans", fontSize=7.3, fillColor=INK))
        for k, color, dy, shape in ((k_any, ANY, 3.2, "circle"), (k_beyond, BEYOND, -3.2, "diamond")):
            share, lo, hi = wilson(k, n)
            d.add(Line(x(lo), ry + dy, x(hi), ry + dy, strokeColor=color, strokeWidth=1.3))
            marker(x(share), ry + dy, color, shape)
            if pooled:
                d.add(String(x(hi) + 4, ry + dy - 2.3, f"{share:.0f}%", fontName="Sans", fontSize=6.6,
                             fillColor=INK))
    ly = h - 8
    marker(x0 + 3, ly + 2.4, ANY, "circle")
    d.add(String(x0 + 10, ly, "Any perceived stereotype", fontName="Sans", fontSize=7.2, fillColor=INK))
    marker(x0 + 128, ly + 2.4, BEYOND, "diamond")
    d.add(String(x0 + 135, ly, "Stereotype beyond casting", fontName="Sans", fontSize=7.2, fillColor=INK))
    d.add(String(x1, ly, "lines: 95% Wilson intervals", fontName="Sans", fontSize=6.8, fillColor=MUTED,
                 textAnchor="end"))
    return d


# ------------------------------------------------------------------------------------ text

story = [
    p("Probing Social Stereotypes in LLM-Generated Stories", TITLE),
    p("Milestone 1 · Project plan and first experiments", SUBTITLE),
    p("Muntean Vlad-Andrei · Strejaru Mihai · Pacuraru Macedoniu Nicolae · 1 November 2026", SUBTITLE),
    Spacer(1, 3),
    Table([[""]], colWidths=[W], rowHeights=[0.6],
          style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.8, RULE)])),

    p("1&nbsp;&nbsp;Problem", H1),
    p("Large language models (LLMs) now write a growing share of everyday fiction, teaching material and "
      "marketing text. Whenever a prompt leaves a character's gender, ethnicity, age or job unspecified, the "
      "model has to fill it in, and its defaults are repeated across millions of generations. If the surgeon "
      "is almost always a man and the night cleaner almost always a minority woman, the model reproduces a "
      "representational harm even though no single sentence is offensive (Blodgett et al., 2020)."),
    p("The project measures which social stereotypes different LLMs lean on when they write short stories from "
      "neutral premises, and compares model families and sizes on the same premises under the same sampling "
      "settings. It also builds a tool that flags stereotypes in new stories together with the evidence a human "
      "needs to check them. Four research questions guide the work:", LEAD),
    *bullets([
        "<b>RQ1</b> How often does a reader perceive a stereotype in stories written from premises that leave "
        "every demographic attribute open, and how does this differ between models?",
        "<b>RQ2</b> Which kinds of stereotype (gender roles, gendered traits, ethnicity, nationality, age, "
        "class, …) appear, and which premises trigger them?",
        "<b>RQ3</b> Do model family and model size change these rates?",
        "<b>RQ4</b> Can an interpretable, semi-supervised classifier reproduce the human labels well enough to "
        "triage new stories, and show the sentences behind each flag?",
    ]),
    p("<b>Scope.</b> English stories of about 250 words; <i>perceived</i> stereotypes (what a careful reader "
      "would say the story leans on), not model intent; text only."),

    p("2&nbsp;&nbsp;State of the art", H1),
    p("<b>Bias in NLP.</b> Blodgett et al. (2020) review 146 papers and find that “bias” is often left "
      "undefined; they ask authors to say which harms they measure and why. Gallegos et al. (2024) organise LLM "
      "fairness work into embedding-, probability- and generation-based metrics and list the datasets for each. "
      "Earlier work showed that static word embeddings already encode occupational and gender stereotypes "
      "(Bolukbasi et al., 2016; Caliskan et al., 2017)."),
    p("<b>Fixed-format benchmarks.</b> StereoSet (Nadeem et al., 2021) and CrowS-Pairs (Nangia et al., 2020) "
      "compare how likely a model finds stereotypical and anti-stereotypical sentences; WinoBias and Winogender "
      "(Zhao et al., 2018; Rudinger et al., 2018) test gendered coreference with occupations; BBQ (Parrish et "
      "al., 2022) tests whether question answering falls back on stereotypes when the context is ambiguous. "
      "Kotek et al. (2023) find that LLMs pick the occupation that matches a gender stereotype three to six "
      "times more often than the other one when resolving an ambiguous pronoun."),
    p("<b>Open-ended generation.</b> Sheng et al. (2019) introduce <i>regard</i>, the social perception of the "
      "group a text talks about, and show that it shifts with the group named in the prompt. BOLD (Dhamala et "
      "al., 2021) scores 23,679 Wikipedia-based prompts with sentiment, toxicity, regard and gender-polarity "
      "classifiers. For stories, Lucy and Bamman (2021) find that GPT-3 ties feminine characters to family and "
      "appearance and gives them less power than masculine ones, and Huang et al. (2021) use commonsense "
      "inference to surface implicit gender bias in narratives. Wan et al. (2023) find gendered language in "
      "LLM-written reference letters, and Cheng et al. (2023) show with “marked personas” that portraits "
      "generated for marked groups rely on othering and stereotyped words."),
    p("<b>Measurement tools.</b> LLMs are increasingly used as annotators and judges. Gilardi et al. (2023) "
      "report that ChatGPT outperforms crowd workers on several text-annotation tasks; Zheng et al. (2023) find "
      "that strong LLM judges agree with humans about as often as humans agree with each other, but also "
      "document position and self-preference biases. Active learning (Settles, 2009) reduces the number of "
      "labels a classifier needs by asking humans about the most informative examples first."),

    p("3&nbsp;&nbsp;Critical analysis", H1),
    p("The existing work leaves five gaps that matter for stereotypes in open-ended stories. Table 1 pairs "
      "each gap with the design decision that addresses it.", LEAD),
]

gaps = [
    ("G1 Recognition is not production",
     "Likelihood and question-answering benchmarks measure whether a model prefers a stereotype when it is "
     "shown one, not what it writes when free to choose; their items also have validity problems (Blodgett et "
     "al., 2021).",
     "Story premises that leave every attribute to the model and never mention bias; the unit of analysis is "
     "the story the model actually writes."),
    ("G2 Automatic proxies miss casting",
     "Sentiment, regard and toxicity are neutral for a story in which every nurse is a woman and every cleaner "
     "an immigrant. Who gets which role, and whether a story depicts or endorses a stereotype, needs readers.",
     "Human-perceived, multi-label annotation (17 labels) with an explicit split between casting and "
     "substantive stereotypes; lexical and demographic analyzers as a second, automatic signal."),
    ("G3 One axis, one family",
     "Most generation studies look at gender only, at a single and often older model family (GPT-2/3), with "
     "their own prompts and sampling settings, so families and sizes cannot be compared.",
     "The same 89 premises (19 categories, 17 stereotype labels) for every model; several families and "
     "sizes; one system prompt and one sampling configuration."),
    ("G4 Unstated annotation rules",
     "Whether stereotypical casting alone counts is usually left to each annotator, so labels drift between "
     "annotators and rounds; the reliability of LLM annotators is rarely reported.",
     "Written casting criteria with reference lists; blind, shuffled batches mixing all models; a subset "
     "read twice under new ids to report Cohen's κ."),
    ("G5 Opaque detectors",
     "Classifiers return a score without the sentence that triggered it, which makes review slow and "
     "error-prone.",
     "An interpretable classifier that shows evidence sentences and top features inside a human-in-the-loop "
     "review queue."),
]
rows = [[p("Gap", CELL_HEAD), p("What is missing", CELL_HEAD), p("Response in this project", CELL_HEAD)]]
rows += [[p(f"<b>{a}</b>", CELL), p(b, CELL), p(c, CELL)] for a, b, c in gaps]
gap_table = styled_table(rows, [3.1 * cm, (W - 3.1 * cm) / 2, (W - 3.1 * cm) / 2])
story += [gap_table,p("Table 1. Gaps in the state of the art and the corresponding design decisions.", CAPTION)]

story += [
    p("4&nbsp;&nbsp;Proposed architecture", H1),
    p("The system is a pipeline from story premises to a per-model report, with a review loop that turns "
      "human decisions on classifier flags into new labels (Figure 1).", LEAD),
    KeepTogether([pipeline_figure(),
                  p("Figure 1. Architecture: generation and storage (top), annotation, models and reporting "
                    "(bottom), and the human-in-the-loop review loop.", CAPTION)]),
    *bullets([
        "<b>Probe bank.</b> 89 premises in 19 categories: occupation, family, traits, nationality, race, "
        "religion, age, disability, class, sexuality, appearance, regional, profession, mental health, "
        "political, saviour narratives, open character lists, cue-free one-line defaults and neutral controls.",
        "<b>Generation.</b> Every model receives the same premises with one prompt and one sampling "
        "configuration. Runs are resumable, and several samples are drawn per premise.",
        "<b>Store.</b> SQLite with stories, every annotation round (with the taxonomy version it used), "
        "classifier predictions and judge scores; everything can be exported and re-imported as JSONL.",
        "<b>Annotation.</b> A web interface for human annotators (multi-label, span highlighting, keyboard "
        "shortcuts) and a batch protocol for LLM annotators. Protocol v2.1 defines casting by explicit "
        "criteria: gender by jobs (C1), rank (C2) and household tasks (C3), and ethnicity or nationality by "
        "status (C4), each with reference lists and exclusions; everything else is judged as substantive.",
        "<b>Classifier.</b> One logistic regression per label over word TF-IDF and 79 stereotype co-occurrence "
        "features (gender cues near job and trait words, out-group terms near negative or positive words), "
        "semi-supervised by self-training on unlabelled stories, with thresholds tuned on out-of-fold "
        "predictions and a lexical prior that fades as labels accumulate. Optional LLM-judge scores are stacked "
        "as extra features. Each flag comes with its evidence sentences and top features.",
        "<b>Analyzers and report.</b> A default-demographics module (protagonist gender, name-based origin, "
        "name diversity) and the lexical analyzer feed a report with per-model rates, 95% Wilson intervals, "
        "per-category and per-premise tables (Markdown, JSON and a web page).",
    ]),

    p("5&nbsp;&nbsp;Data and processing", H1),
    p("<b>Data.</b> All text is generated for the study: there is no scraped or personal data. The model set "
      "spans two groups: proprietary Claude models (Haiku, Sonnet, Opus) and open-weight models (Gemma 4 E4B, "
      "Qwen3.5 4B, 9B and 27B, Mistral 7B, OLMo 3 7B, OLMo 3.1 32B, gpt-oss 20B). Each open-weight model writes "
      "three stories per premise (267 per model) and each Claude model at least one (89); 2,714 stories have been "
      "generated so far. Labels come from blind annotators following the written protocol; LLM annotators "
      "stand in for human readers until people spot-check their labels."),
    p("<b>Processing.</b> Each step is scripted and can be rerun:", LEAD),
    *bullets([
        "<b>Prompting.</b> Premise plus a fixed instruction (about 250 words, every character named, no title "
        "or commentary) and a fixed system prompt that asks only for good fiction.",
        "<b>Generation.</b> Sampling with temperature 0.9, top-p 0.95, no top-k and at most 700 new tokens "
        "(1,500 for gpt-oss, whose reasoning counts against the limit), with thinking mode off where a model "
        "allows it.",
        "<b>Cleaning.</b> Strip reasoning blocks, titles and code fences; drop outputs under 20 words; "
        "deduplicate on a hash of model, premise and text; keep the raw output for auditing.",
        "<b>Sampling for annotation.</b> One story per premise per model; batches are shuffled under anonymous "
        "ids and every batch mixes all models, so annotator leniency cannot favour one family.",
        "<b>Validation.</b> Labels must belong to the taxonomy, and every label needs an exact quote that is "
        "located in the story and stored as a span; stories repeated under new ids measure agreement.",
        "<b>Training and evaluation.</b> 5-fold cross-validation over labelled stories (unlabelled stories stay "
        "on the training side); per-label precision, recall and F1, macro and micro F1, and bias-versus-none "
        "accuracy.",
        "<b>Reporting.</b> Any-label and beyond-casting rates per model with Wilson intervals, gaps between "
        "families with intervals from resampling premises, per-category breakdowns and agreement between readers.",
    ]),

    p("6&nbsp;&nbsp;Progress and first experiments", H1),
    p("The pipeline of Section 4 runs end to end: a Python package with a command-line tool and a web interface "
      "for annotation and review, covered by 48 automated tests, with the code and all data in one shared "
      "repository. We ran basic experiments to check that the plan works. Eleven models from six families wrote "
      "2,714 stories, and one story per premise and model (979 stories) was read in one round under protocol "
      "v2.1, in 22 blind batches holding the same mix of models. The readers are Claude Opus instances standing "
      "in for people (Figure 2)."),
    *bullets([
        "<b>The measures separate the models (RQ1, RQ2).</b> Beyond casting, open-weight stories are at 26% against "
        "7% for Claude, a gap of 19 points (95% interval +14 to +24, resampling premises). Stereotypical casting "
        "does not differ between the two groups (−1 point, −7 to +5), so the gap lies in what characters do and "
        "are like.",
        "<b>Family matters more than size (RQ3).</b> Mistral is highest (49%) and OLMo closest to Claude (14%). "
        "Qwen3.5 4B, 9B and 27B are at 34%, 24% and 27%, with overlapping intervals.",
        "<b>The automatic measures add a second signal.</b> Qwen3.5 makes the protagonist a man in 70–73% of "
        "stories, while OLMo 7B and gpt-oss lean the other way (30% and 33%). Qwen3.5 also puts a character called "
        "Elias into 41–57% of its stories.",
        "<b>The classifier is a working baseline, not yet a substitute for readers (RQ4).</b> On 1,338 labelled "
        "stories, macro-F1 is 0.21, or 0.28 with scores from an LLM judge (Phi-4). Bias-versus-none accuracy "
        "reaches 62%, barely above the 60% of always answering “none”. The judge mostly recognises the topic: its "
        "mean AUC of 0.80 falls to 0.61 between stories from the same premise.",
    ]),
    KeepTogether([results_figure(),
                  p("Figure 2. Share of stories with at least one perceived stereotype and with a stereotype beyond "
                    "casting, one story per premise and model.", CAPTION)]),
    p("<b>Reliability and limits.</b> On 44 stories read twice under new ids, readers agree on “any label or none” "
      "for 41 (κ 0.85), and in a pilot two independent groups reached κ 0.95 on casting decisions. This is "
      "agreement between LLM readers, and Claude reading Claude's stories may favour them, so the results are "
      "preliminary until people check the labels. Claude's sampling settings and system prompt could not be fixed "
      "like the open-weight models', and with 89 stories per model the per-model intervals are about ±10 points. "
      "Even so, the experiments show that the method runs from premise to report and detects differences between "
      "model families."),

    p("References", H1),
]

refs = [
    "Blodgett, S. L., Barocas, S., Daumé III, H., &amp; Wallach, H. (2020). Language (technology) is power: A "
    "critical survey of “bias” in NLP. <i>Proceedings of ACL 2020</i>.",
    "Blodgett, S. L., Lopez, G., Olteanu, A., Sim, R., &amp; Wallach, H. (2021). Stereotyping Norwegian salmon: "
    "An inventory of pitfalls in fairness benchmark datasets. <i>Proceedings of ACL-IJCNLP 2021</i>.",
    "Bolukbasi, T., Chang, K.-W., Zou, J., Saligrama, V., &amp; Kalai, A. (2016). Man is to computer programmer "
    "as woman is to homemaker? Debiasing word embeddings. <i>Advances in NeurIPS 29</i>.",
    "Caliskan, A., Bryson, J. J., &amp; Narayanan, A. (2017). Semantics derived automatically from language "
    "corpora contain human-like biases. <i>Science, 356</i>(6334).",
    "Cheng, M., Durmus, E., &amp; Jurafsky, D. (2023). Marked personas: Using natural language prompts to "
    "measure stereotypes in language models. <i>Proceedings of ACL 2023</i>.",
    "Dhamala, J., Sun, T., Kumar, V., Krishna, S., Pruksachatkun, Y., Chang, K.-W., &amp; Gupta, R. (2021). "
    "BOLD: Dataset and metrics for measuring biases in open-ended language generation. <i>Proceedings of FAccT "
    "2021</i>.",
    "Gallegos, I. O., Rossi, R. A., Barrow, J., Tanjim, M. M., Kim, S., Dernoncourt, F., Yu, T., Zhang, R., "
    "&amp; Ahmed, N. K. (2024). Bias and fairness in large language models: A survey. <i>Computational "
    "Linguistics, 50</i>(3).",
    "Gilardi, F., Alizadeh, M., &amp; Kubli, M. (2023). ChatGPT outperforms crowd workers for text-annotation "
    "tasks. <i>PNAS, 120</i>(30).",
    "Huang, T., Brahman, F., Shwartz, V., &amp; Chaturvedi, S. (2021). Uncovering implicit gender bias in "
    "narratives through commonsense inference. <i>Findings of EMNLP 2021</i>.",
    "Kotek, H., Dockum, R., &amp; Sun, D. Q. (2023). Gender bias and stereotypes in large language models. "
    "<i>Proceedings of the ACM Collective Intelligence Conference (CI ’23)</i>.",
    "Lucy, L., &amp; Bamman, D. (2021). Gender and representation bias in GPT-3 generated stories. "
    "<i>Proceedings of the Third Workshop on Narrative Understanding</i>.",
    "Nadeem, M., Bethke, A., &amp; Reddy, S. (2021). StereoSet: Measuring stereotypical bias in pretrained "
    "language models. <i>Proceedings of ACL-IJCNLP 2021</i>.",
    "Nangia, N., Vania, C., Bhalerao, R., &amp; Bowman, S. R. (2020). CrowS-Pairs: A challenge dataset for "
    "measuring social biases in masked language models. <i>Proceedings of EMNLP 2020</i>.",
    "Parrish, A., Chen, A., Nangia, N., Padmakumar, V., Phang, J., Thompson, J., Htut, P. M., &amp; Bowman, "
    "S. R. (2022). BBQ: A hand-built bias benchmark for question answering. <i>Findings of ACL 2022</i>.",
    "Rudinger, R., Naradowsky, J., Leonard, B., &amp; Van Durme, B. (2018). Gender bias in coreference "
    "resolution. <i>Proceedings of NAACL-HLT 2018</i>.",
    "Settles, B. (2009). <i>Active learning literature survey</i> (Computer Sciences Technical Report 1648). "
    "University of Wisconsin–Madison.",
    "Sheng, E., Chang, K.-W., Natarajan, P., &amp; Peng, N. (2019). The woman worked as a babysitter: On "
    "biases in language generation. <i>Proceedings of EMNLP-IJCNLP 2019</i>.",
    "Wan, Y., Pu, G., Sun, J., Garimella, A., Chang, K.-W., &amp; Peng, N. (2023). “Kelly is a warm person, "
    "Joseph is a role model”: Gender biases in LLM-generated reference letters. <i>Findings of EMNLP 2023</i>.",
    "Zhao, J., Wang, T., Yatskar, M., Ordonez, V., &amp; Chang, K.-W. (2018). Gender bias in coreference "
    "resolution: Evaluation and debiasing methods. <i>Proceedings of NAACL-HLT 2018</i>.",
    "Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., "
    "Zhang, H., Gonzalez, J. E., &amp; Stoica, I. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot "
    "Arena. <i>Advances in NeurIPS 36, Datasets and Benchmarks Track</i>.",
]
story += [p(r, REF) for r in refs]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Sans", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(2.0 * cm, 1.15 * cm, "Probing Social Stereotypes in LLM-Generated Stories · Milestone 1")
    canvas.drawRightString(A4[0] - 2.0 * cm, 1.15 * cm, f"{doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm, topMargin=1.7 * cm,
                        bottomMargin=1.8 * cm, title="Probing Social Stereotypes in LLM-Generated Stories: "
                        "Milestone 1 plan", author="Muntean Vlad-Andrei, Strejaru Mihai, Pacuraru Macedoniu Nicolae",
                        subject="Project plan: problem, state of the art, critical analysis, architecture, data "
                                "and processing; first experiments")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(f"wrote {OUT}")
