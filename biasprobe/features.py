"""Stereotype co-occurrence features and evidence extraction.

The analyzer splits a story into sentences, matches each sentence against the
lexicons and counts how often e.g. a male cue and a stereotypically male job,
or a nationality and a negative term, appear in the same sentence. The counts
become numeric features; the matching sentences become highlightable evidence.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from . import lexicons as lx

_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n+|$)")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


@dataclass
class Evidence:
    label: str
    feature: str
    start: int
    end: int
    sentence: str
    cues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "feature": self.feature, "start": self.start,
                "end": self.end, "sentence": self.sentence, "cues": self.cues}


@dataclass
class Analysis:
    features: dict[str, float]
    evidence: list[Evidence]
    counts: dict[str, int]


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    out = []
    for m in _SENTENCE_RE.finditer(text):
        s = m.group(0)
        stripped = s.strip()
        if not stripped:
            continue
        start = m.start() + (len(s) - len(s.lstrip()))
        out.append((start, start + len(stripped), stripped))
    return out


def _compile(terms: Iterable[str], flags: int = re.IGNORECASE) -> re.Pattern:
    escaped = sorted((re.escape(t).replace(r"\ ", r"\s+") for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(escaped) + r")(?![A-Za-z])", flags)


class LexiconMatcher:
    def __init__(self) -> None:
        self.patterns: dict[str, re.Pattern] = {name: _compile(terms) for name, terms in lx.LEXICONS.items()}
        self.male_names = _compile(lx.MALE_NAMES, flags=0)
        self.female_names = _compile(lx.FEMALE_NAMES, flags=0)

    def spans(self, name: str, text: str) -> list[tuple[int, int, str]]:
        found = [(m.start(), m.end(), m.group(0).lower()) for m in self.patterns[name].finditer(text)]
        if name == "male":
            found += [(m.start(), m.end(), m.group(0)) for m in self.male_names.finditer(text)]
        elif name == "female":
            found += [(m.start(), m.end(), m.group(0)) for m in self.female_names.finditer(text)]
        return found

    def matches(self, name: str, text: str) -> list[str]:
        return [term for _, _, term in self.spans(name, text)]


_MATCHER: LexiconMatcher | None = None


def matcher() -> LexiconMatcher:
    global _MATCHER
    if _MATCHER is None:
        _MATCHER = LexiconMatcher()
    return _MATCHER


GENDER_PAIRS = [
    # (name, gender lexicon, other lexicon, label, stereotypical?)
    ("male_x_male_job", "male", "male_job", "gender_role", True),
    ("female_x_female_job", "female", "female_job", "gender_role", True),
    ("male_x_female_job", "male", "female_job", "gender_role", False),
    ("female_x_male_job", "female", "male_job", "gender_role", False),
    ("male_x_agentic", "male", "agentic", "gender_trait", True),
    ("female_x_communal", "female", "communal", "gender_trait", True),
    ("female_x_female_negative", "female", "female_negative", "gender_trait", True),
    ("male_x_male_negative", "male", "male_negative", "gender_trait", True),
    ("female_x_agentic", "female", "agentic", "gender_trait", False),
    ("male_x_communal", "male", "communal", "gender_trait", False),
]

GENDER_TARGETS = ["male_job", "female_job", "agentic", "communal", "female_negative", "male_negative"]

COUNT_FEATURES = [f"n_{name}" for name in lx.LEXICONS]
PAIR_FEATURES = [p[0] for p in GENDER_PAIRS] + list(lx.PAIRED_FEATURES)
DERIVED_FEATURES = [
    "gender_role_stereo", "gender_role_counter", "gender_role_ratio",
    "gender_trait_stereo", "gender_trait_counter", "gender_trait_ratio",
    "male_share", "outgroup_neg_ratio", "n_sentences", "n_words",
]
FEATURE_NAMES: list[str] = COUNT_FEATURES + PAIR_FEATURES + DERIVED_FEATURES


def analyze(text: str) -> Analysis:
    m = matcher()
    sentences = split_sentences(text)
    counts: dict[str, int] = {name: 0 for name in lx.LEXICONS}
    pair_counts: dict[str, int] = {name: 0 for name in PAIR_FEATURES}
    evidence: list[Evidence] = []

    for start, end, sentence in sentences:
        spans = {name: m.spans(name, sentence) for name in lx.LEXICONS}
        hits = {name: [t for _, _, t in found] for name, found in spans.items()}
        for name, found in hits.items():
            counts[name] += len(found)

        # Gender pairs: attribute each job/trait mention to the *nearest* gender
        # cue in the sentence, so "Dr. Harris, the surgeon, snapped at nurse Emily"
        # yields male+surgeon and female+nurse rather than every combination.
        gender_cues = [((s + e) / 2.0, "male", t) for s, e, t in spans["male"]]
        gender_cues += [((s + e) / 2.0, "female", t) for s, e, t in spans["female"]]
        seen_pairs: dict[str, set[str]] = {}
        if gender_cues:
            for other in GENDER_TARGETS:
                for s, e, term in spans[other]:
                    pos = (s + e) / 2.0
                    _dist, gender, cue = min((abs(c - pos), g, t) for c, g, t in gender_cues)
                    key = f"{gender}_x_{other}"
                    if key in pair_counts:
                        pair_counts[key] += 1
                        seen_pairs.setdefault(key, set()).update([cue, term])
        for name, _gender, _other, label, stereo in GENDER_PAIRS:
            if stereo and name in seen_pairs:
                evidence.append(Evidence(label, name, start, end, sentence,
                                         cues=sorted(seen_pairs[name])[:6]))

        for name, (first, second, label) in lx.PAIRED_FEATURES.items():
            if hits[first] and hits[second]:
                pair_counts[name] += 1
                if label:
                    evidence.append(Evidence(label, name, start, end, sentence,
                                             cues=sorted(set(hits[first][:3] + hits[second][:3]))))

    role_stereo = pair_counts["male_x_male_job"] + pair_counts["female_x_female_job"]
    role_counter = pair_counts["male_x_female_job"] + pair_counts["female_x_male_job"]
    trait_stereo = (pair_counts["male_x_agentic"] + pair_counts["female_x_communal"]
                    + pair_counts["female_x_female_negative"] + pair_counts["male_x_male_negative"])
    trait_counter = pair_counts["female_x_agentic"] + pair_counts["male_x_communal"]
    outgroup_neg = (pair_counts["natl_x_neg"] + pair_counts["immig_x_neg"]
                    + pair_counts["ethn_x_neg"] + pair_counts["relig_x_neg"])
    outgroup_pos = pair_counts["natl_x_pos"] + pair_counts["immig_x_pos"] + pair_counts["ethn_x_pos"]
    n_words = len(_WORD_RE.findall(text))

    features: dict[str, float] = {}
    for name in lx.LEXICONS:
        features[f"n_{name}"] = math.log1p(counts[name])
    for name in PAIR_FEATURES:
        features[name] = math.log1p(pair_counts[name])
    features["gender_role_stereo"] = math.log1p(role_stereo)
    features["gender_role_counter"] = math.log1p(role_counter)
    features["gender_role_ratio"] = role_stereo / (role_stereo + role_counter + 1.0)
    features["gender_trait_stereo"] = math.log1p(trait_stereo)
    features["gender_trait_counter"] = math.log1p(trait_counter)
    features["gender_trait_ratio"] = trait_stereo / (trait_stereo + trait_counter + 1.0)
    features["male_share"] = counts["male"] / (counts["male"] + counts["female"] + 1.0)
    features["outgroup_neg_ratio"] = outgroup_neg / (outgroup_neg + outgroup_pos + 1.0)
    features["n_sentences"] = math.log1p(len(sentences))
    features["n_words"] = math.log1p(n_words)
    return Analysis(features=features, evidence=evidence, counts={**counts, **pair_counts})


def feature_vector(text: str) -> np.ndarray:
    feats = analyze(text).features
    return np.array([feats[name] for name in FEATURE_NAMES], dtype=float)


class StereotypeFeaturizer(BaseEstimator, TransformerMixin):
    """sklearn transformer: list of samples -> dense (n, len(FEATURE_NAMES)) array.
    A sample is either a string or a dict with a `text` key."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = [feature_vector(_text_of(x)) for x in X]
        if not rows:
            return np.zeros((0, len(FEATURE_NAMES)))
        return np.vstack(rows)

    def get_feature_names_out(self, input_features=None):
        return np.array(FEATURE_NAMES, dtype=object)


class TextSelector(BaseEstimator, TransformerMixin):
    """Pull the text out of each sample so TfidfVectorizer can consume it."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return [_text_of(x) for x in X]

    def get_feature_names_out(self, input_features=None):
        return np.array(["text"], dtype=object)


class JudgeFeaturizer(BaseEstimator, TransformerMixin):
    """Expose LLM-judge scores (if a sample carries them) as features, plus a
    flag saying whether the judge scores were available at all."""

    def __init__(self, labels: list[str]):
        self.labels = labels

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        out = np.zeros((len(X), len(self.labels) + 1))
        for i, x in enumerate(X):
            judge = x.get("judge") if isinstance(x, dict) else None
            if judge:
                out[i, -1] = 1.0
                for j, label in enumerate(self.labels):
                    out[i, j] = float(judge.get(label, 0.0) or 0.0)
        return out

    def get_feature_names_out(self, input_features=None):
        return np.array([f"judge_{l}" for l in self.labels] + ["judge_available"], dtype=object)


def _text_of(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("text", "")
    return str(x)
