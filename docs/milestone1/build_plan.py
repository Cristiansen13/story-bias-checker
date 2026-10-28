"""Build the Milestone 1 project plan (PDF, A4) for the biasprobe study.

usage: python docs/milestone1/build_plan.py   ->   docs/milestone1/milestone1_plan.pdf
Needs reportlab and the Windows fonts Georgia and Segoe UI.
"""

import math
from pathlib import Path

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
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
CELL_NUM = ParagraphStyle("cellnum", parent=CELL, alignment=TA_CENTER)
CELL_NUM_HEAD = ParagraphStyle("cellnumhead", parent=CELL_HEAD, alignment=TA_CENTER)
CELL_GROUP = ParagraphStyle("cellgroup", fontName="Sans-Bold", fontSize=7.8, leading=10, textColor=MUTED)
CAPTION = ParagraphStyle("caption", fontName="Body-Italic", fontSize=8.2, leading=10.4, textColor=MUTED,
                         spaceBefore=2, spaceAfter=5)
REF = ParagraphStyle("ref", fontName="Body", fontSize=7.9, leading=9.9, textColor=INK, leftIndent=12,
                     firstLineIndent=-12, spaceAfter=1.6, alignment=TA_LEFT)

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
    box(xs[1], top_y, "2  Generation", ["API client: OpenAI-compatible, Ollama", "HF batch jobs on the Slurm GPU cluster",
                                         "one prompt + sampling for all models"])
    box(xs[2], top_y, "3  Clean & store", ["strip reasoning blocks and titles", "drop short outputs, deduplicate",
                                            "SQLite: stories, all annotation rounds"])
    box(xs[2], bot_y, "4  Blind annotation", ["17 labels, casting criteria C1–C4", "exact evidence quotes \u2192 spans",
                                               "hidden anchors, double annotation (\u03ba)"])
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


# one story per premise and model, labelled blind (Claude: round 3, open-weight: round 2):
# (model, stories with any label, stories with a stereotype beyond casting, stories)
RATES = [
    ("Claude (round-3 labels)", [("Haiku", 35, 15, 89), ("Sonnet", 32, 17, 89), ("Opus", 27, 12, 89),
                                 ("All Claude", 94, 44, 267)]),
    ("Open-weight (round-2 labels)", [("Gemma 4 E4B", 36, 15, 89), ("Qwen3.5 4B", 35, 25, 89),
                                      ("Qwen3.5 9B", 36, 23, 89), ("Qwen3.5 27B", 39, 23, 89),
                                      ("All open-weight", 146, 86, 356)]),
]


def results_figure():
    pitch, label_w, xmax = 14.5, 112, 60
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
    p("Milestone 1 · Project plan, current implementation and preliminary results", SUBTITLE),
    p("Mihai Strejaru · 27 October 2026", SUBTITLE),
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
     "Written casting criteria with reference lists; blind, shuffled batches mixing all models; hidden "
     "anchors to measure drift; double annotation on a subset to report Cohen's κ."),
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
        "<b>Generation.</b> Two interchangeable back-ends behind one prompt and one sampling configuration: an "
        "HTTP client for OpenAI-compatible, Ollama or custom gateways, and a batched Hugging Face generator "
        "for open-weight checkpoints on the university's Slurm cluster (NVIDIA A100 80 GB, Apptainer "
        "containers). Runs are resumable, and checkpoints are rejected if any weights fail to load.",
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
      "spans two groups: proprietary Claude models (Haiku, Sonnet, Opus) and open-weight models run on the "
      "cluster (Gemma 4 E4B, Qwen3.5 4B, 9B and 27B), to be extended with further open families (Llama, "
      "Mistral, OLMo, gpt-oss). Each model writes three stories per premise (267 per model); 1,380 stories "
      "have been generated so far. Labels come from blind annotators following the written protocol; LLM "
      "annotators stand in for human readers until people spot-check their labels."),
    p("<b>Processing.</b> Each step is scripted and can be rerun:", LEAD),
    *bullets([
        "<b>Prompting.</b> Premise plus a fixed instruction (about 250 words, every character named, no title "
        "or commentary) and a fixed system prompt that asks only for good fiction.",
        "<b>Generation.</b> Batched sampling with temperature 0.9, top-p 0.95, no top-k and at most 700 new "
        "tokens, thinking mode off; samples of each premise are generated in rounds so a cut-short run stays "
        "balanced.",
        "<b>Cleaning.</b> Strip reasoning blocks, titles and code fences; drop outputs under 20 words; "
        "deduplicate on a hash of model, premise and text; keep the raw output for auditing.",
        "<b>Sampling for annotation.</b> One story per premise per model; batches are shuffled under anonymous "
        "ids and every batch mixes all models, so annotator leniency cannot favour one family.",
        "<b>Validation.</b> Labels must belong to the taxonomy, and every label needs an exact quote that is "
        "located in the story and stored as a span; anchors from earlier rounds measure drift.",
        "<b>Training and evaluation.</b> 5-fold cross-validation over labelled stories (unlabelled stories stay "
        "on the training side); per-label precision, recall and F1, macro and micro F1, and bias-versus-none "
        "accuracy.",
        "<b>Reporting.</b> Any-label and beyond-casting rates per model with Wilson intervals, two-proportion "
        "tests between families, per-category breakdowns and inter-annotator agreement.",
    ]),

    p("6&nbsp;&nbsp;Current implementation", H1),
    p("The architecture of Section 4 is implemented as a Python package (about 4,800 lines including the "
      "cluster scripts) and has been used for two studies. It is driven by one command-line tool whose 16 "
      "commands cover the whole pipeline, from configuration, generation and import of offline generations to "
      "training, prediction and the report, and by a FastAPI web application for annotation, review and "
      "reporting. Table 2 lists the components and their state.", LEAD),
]

components = [
    ("Probe bank", "prompts.py: 89 premises in 19 categories; exported as JSONL for offline generators.",
     "Complete."),
    ("API generation", "llm_client.py, generate.py: OpenAI-compatible, Ollama and custom request templates; "
     "parallel, resumable, retried and deduplicated.",
     "Complete; not yet run against a remote server (the Claude stories were written by subagents)."),
    ("Cluster generation", "generate_hf.py and generate.sbatch: batched Hugging Face sampling in the shared "
     "Apptainer container on one A100, a smoke pass over all models first, resumable; import-generations "
     "cleans and loads the output.",
     "Used for study 2: four models, 1,068 stories in one 35-minute job."),
    ("Store", "storage.py: SQLite tables for stories, annotations (every round, with its taxonomy version and "
     "spans), predictions and judge scores; JSONL export and import.",
     "1,436 stories (1,380 generated, 56 demo), 715 of them annotated."),
    ("Annotation", "Web interface (annotate, review flags, check a new story, browse, report) and a batch "
     "workflow for LLM annotators with anonymous ids, mixed batches, hidden anchors and quote-to-span "
     "validation.",
     "Three rounds and a pilot run with LLM annotators; no human annotators yet."),
    ("Classifier", "features.py, model.py: TF-IDF and 79 co-occurrence features, self-training, out-of-fold "
     "thresholds, fading lexical prior, evidence sentences and top features per flag.",
     "Trained on 715 labelled stories; too weak to use without review (Section 8)."),
    ("LLM judge", "judge.py: per-label scores from 0 to 1, stacked as classifier features.",
     "Implemented and tested; not run yet."),
    ("Analyzers and report", "demographics.py, analysis.py: protagonist gender, name-based origin, name "
     "diversity and reuse, gender–job and out-group co-occurrence; Markdown, JSON and web report.",
     "Complete; source of the automatic measures in Section 8."),
    ("Tests", "46 pytest tests with a mocked LLM server and no network access.", "All pass."),
]
rows = [[p("Component", CELL_HEAD), p("Implementation", CELL_HEAD), p("State", CELL_HEAD)]]
rows += [[p(f"<b>{a}</b>", CELL), p(b, CELL), p(c, CELL)] for a, b, c in components]
story += [styled_table(rows, [2.9 * cm, W - 2.9 * cm - 5.0 * cm, 5.0 * cm]),
          p("Table 2. Components of the current implementation and their state (28 October 2026).", CAPTION)]

story += [
    p("<b>Annotation workflow.</b> Until people annotate, the readers are Claude Opus subagents. A script draws "
      "the stories, gives them anonymous ids, shuffles them into batches of about 45 that mix every model of "
      "the round, and hides anchors from earlier rounds among them. Each annotator receives only the protocol, "
      "the taxonomy and one batch of story texts, and returns labels, a note and one exact quote per label as "
      "JSON. The import script rejects unknown labels, locates every quote in its story and stores it as a "
      "span, stores the targets, and scores the anchors for drift without storing them."),
    p("<b>Repository.</b> Code, tests, cluster scripts, the annotation protocols and this document are kept in a "
      "git repository. The working data (database, records of each annotation round, raw cluster outputs and "
      "database backups) are kept outside it."),

    p("7&nbsp;&nbsp;Methodology so far", H1),
    p("Two studies have been run with the same 89 premises and the same taxonomy, and their stories have been "
      "annotated in four rounds (Table 3).", LEAD),
    *bullets([
        "<b>Study 1 (Claude).</b> Claude Haiku, Sonnet and Opus, each driven by a subagent that received the "
        "premises verbatim and was told only to write good fiction: the 63 original premises once, then 26 new "
        "premises and a second sample of the 15 premises that had triggered the most bias; 104 stories per "
        "model, 312 in total.",
        "<b>Study 2 (open-weight).</b> Gemma 4 E4B and Qwen3.5 4B, 9B and 27B on the cluster, with the sampling "
        "settings of Section 5 and three independent samples per premise: 267 stories per model, 1,068 in "
        "total. None reached the token limit or was dropped as too short.",
        "<b>Annotation.</b> Readers see the story text only; they label what the story portrays rather than "
        "what it is about, count stereotypical casting and mark it “casting only”, and quote one exact passage "
        "per label. For the comparison between families, one story per premise and model is annotated (the "
        "first sample), so every model is measured on the same 89 premises.",
        "<b>Measures.</b> The share of stories with at least one label and the share with a stereotype beyond "
        "casting (labelled, and the note does not say “casting only”), with 95% Wilson intervals and "
        "two-proportion z-tests between families; Cohen's κ between rounds and between annotator groups. "
        "Automatic measures over all stories: protagonist (most-mentioned named character) gender, name-based "
        "origin, distinct character names (mean over 50 random subsamples of 104 stories, so that every model is "
        "measured on the same sample size) and the stereotypical share of gender–job pairs. The classifier is "
        "evaluated by 5-fold cross-validation.",
    ]),
]

rounds = [
    ("Study 1", "312 Claude stories; the first batch annotated twice (11, then 17 labels)", "none",
     "Opus subagents", "v1"),
    ("Round 2", "356 open-weight stories, one per premise and model", "30 study-1 Claude stories",
     "8 subagents", "v1"),
    ("Round 3", "267 Claude stories, one per premise and model", "40 round-2 open-weight stories",
     "7 subagents", "v1"),
    ("Pilot", "79 stories: 59 that rounds 1–3 labelled differently and 20 they agreed on",
     "none; two independent groups", "2 groups of 2", "v2: casting criteria C1–C4"),
]
rows = [[p(h, CELL_HEAD) for h in ("Round", "Stories annotated", "Hidden anchors", "Readers", "Protocol")]]
rows += [[p(f"<b>{r[0]}</b>", CELL)] + [p(c, CELL) for c in r[1:]] for r in rounds]
story += [KeepTogether([
    styled_table(rows, [1.7 * cm, W - 1.7 * cm - 3.8 * cm - 2.5 * cm - 2.9 * cm, 3.8 * cm, 2.5 * cm, 2.9 * cm]),
    p("Table 3. Annotation rounds. Protocol v2.1 adds the fixes found in the pilot and has not been used for a "
      "full round yet.", CAPTION)])]

story += [
    p("8&nbsp;&nbsp;Preliminary results", H1),
    p("The readers are LLMs and each model has 89 annotated stories, so these results are preliminary: they "
      "show the size of the effects and where the method needs work, not final rates (Figure 2, Table 4).",
      LEAD),
    KeepTogether([results_figure(),
                  p("Figure 2. Share of stories with at least one perceived stereotype and with a stereotype "
                    "beyond casting, one story per premise and model. Round 3 counted casting more readily "
                    "than round 2, so compare the families on the diamonds, which both rounds measure "
                    "alike.", CAPTION)]),
]

models = ["Haiku", "Sonnet", "Opus", "Gemma 4 E4B", "Qwen3.5 4B", "Qwen3.5 9B", "Qwen3.5 27B"]
measures = [
    ("Perceived by readers, 89 stories per model (%)", None),
    ("Any perceived stereotype", [39, 36, 30, 40, 39, 40, 44]),
    ("Stereotype beyond casting", [17, 19, 13, 17, 28, 26, 26]),
    ("Gender roles / occupations", [20, 8, 12, 26, 18, 19, 22]),
    ("Racial / ethnic", [11, 15, 10, 2, 2, 1, 3]),
    ("Labelled stories that are casting only", [57, 47, 56, 58, 29, 36, 41]),
    ("Automatic, all stories (%, names as counts)", None),
    ("Male protagonist", [48, 50, 43, 54, 73, 70, 70]),
    ("Stories with any non-Western name", [57, 68, 66, 18, 29, 29, 42]),
    ("Distinct names per 104 stories", [174, 190, 211, 77, 52, 61, 57]),
    ("Stereotypical share of gender–job pairs", [62, 58, 52, 69, 67, 68, 68]),
]
rows = [[p("Measure", CELL_HEAD)] + [p(m, CELL_NUM_HEAD) for m in models]]
spans = []
for label, values in measures:
    if values is None:
        spans += [("SPAN", (0, len(rows)), (-1, len(rows))), ("BACKGROUND", (0, len(rows)), (-1, len(rows)), BAND)]
        rows.append([p(label, CELL_GROUP)] + [""] * len(models))
    else:
        rows.append([p(label, CELL)] + [p(str(v), CELL_NUM) for v in values])
first_w = 5.6 * cm
story += [KeepTogether([
    styled_table(rows, [first_w] + [(W - first_w) / len(models)] * len(models), spans),
    p("Table 4. Results per model. Claude has 104 stories per model and each open-weight model 267 for the "
      "automatic rows; distinct names are counted on equal subsamples.", CAPTION)])]

story += [
    *bullets([
        "<b>Open-weight stories are perceived as stereotyped more often, but the gap depends on how casting is "
        "counted.</b> Beyond casting, the measure on which study 1 and round 3 give Claude the same rate, the "
        "open-weight models are at 24% (20–29) against 16% (13–21) for Claude (z ≈ 2.3). On any label the gap "
        "is 6 points across rounds (41% against 35%, z = 1.5) and about 28 points within either round. The "
        "direction is robust; the size is not.",
        "<b>The families lean on different stereotypes.</b> Gender casting dominates the open-weight stories "
        "(21% against 13%), together with nationality tropes (3–6% against 0–1%). Claude's stories carry ethnic "
        "casting far more often (10–15% against 1–3%): the cleaner, the cab driver or the ship's cook is the one "
        "character with a minority name. The open-weight models avoid this mostly because their characters "
        "rarely have an ethnicity at all.",
        "<b>Narrow defaults.</b> Qwen3.5 makes the protagonist a man in 70–73% of all stories (Claude 43–50%), "
        "and only 18–42% of open-weight stories contain any non-Western name (Claude 57–68%). The open-weight "
        "models also reuse names: 52–77 distinct names per 104 stories against 174–211, and Qwen3.5 puts a "
        "character called Elias into 41–57% of its stories at every size.",
        "<b>Size does not help.</b> Qwen3.5 4B, 9B and 27B are at 39%, 40% and 44% on any label, with 73%, 70% "
        "and 70% male protagonists.",
        "<b>Premises.</b> Occupation, age, nationality and family premises trigger the open-weight models most; "
        "race, class, regional and saviour premises trigger Claude. A boss dictating to a secretary, a "
        "grandmother with a smartphone and a wedding table of professionals produce a label from every model of "
        "both families. The neutral controls stay mostly clean: 4 of 28 stories labelled, 3 of them by "
        "Qwen3.5 27B.",
    ]),
    p("<b>Reliability.</b> On the 267 Claude stories, round 3 and study 1 agree on “any label or none” for 88% "
      "of stories (κ 0.72); per label κ is 0.79 for gender roles and 0.75 for racial/ethnic. The rounds differ "
      "in how readily they count casting (round 2 strictest, round 3 most lenient), which is why the any-label "
      "comparison between families moves with the round. With the explicit casting criteria, two independent "
      "groups made the same casting decision on 96% of the pilot stories (κ 0.95), against 85% (κ 0.42) for "
      "substantive labels on the hard cases; the pilot also exposed two gaps in the criteria, fixed in v2.1."),
    p("<b>Classifier.</b> Trained on the 715 labelled stories, it reaches macro-F1 0.16, micro-F1 0.26 and 51% "
      "bias-versus-none accuracy in 5-fold cross-validation, no better than with half the labels (0.19, 0.27, "
      "50%). Gender roles improve (F1 0.39, 127 positives) but racial/ethnic labels do not (0.19, 50 "
      "positives): casting depends on who gets which role, which word features barely see. The flags are not "
      "yet a substitute for annotation; the LLM judge is the next signal to add."),
    p("<b>Threats to validity.</b> Every agreement figure is agreement between LLM readers; people should "
      "spot-check the labels before anything is published. The Claude stories were written by subagents that "
      "produced many stories in one context and could avoid names and castings they had already used, while "
      "the open-weight models sampled every story independently; this favours Claude on name diversity and "
      "probably on casting variety. Claude's 104 stories over-weight the 15 resampled premises, which pushes its "
      "rates up. Name-based origin is a coarse signal, and with 89 stories per model the per-model intervals "
      "are about ±10 points."),

    p("9&nbsp;&nbsp;Next steps", H1),
    p("<b>M2:</b> a balanced annotation round under protocol v2.1 in which every batch holds the same mix of all "
      "seven models (623 one-per-premise stories), so that neither round leniency nor contrast between families "
      "can move the comparison; for a like-for-like comparison, Claude stories generated one call at a time "
      "with the same sampling settings as the open-weight models; and two to three further open-weight "
      "families (Llama, Mistral, OLMo, gpt-oss). <b>M3:</b> an LLM judge from a family that is not under test, "
      "the classifier with judge features, and a human spot-check of the LLM labels, starting with the casting "
      "rule. <b>M4:</b> final analysis and report."),

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
                        "Milestone 1 plan", author="Mihai Strejaru",
                        subject="Project plan: problem, state of the art, critical analysis, architecture, data "
                                "and processing; current implementation, methodology and preliminary results")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(f"wrote {OUT}")
