"""Default-demographics analysis: which names, origins and genders does a model
reach for when the premise gives no cue?

This is a corpus-level pattern, not a per-story label. The signal is coarse
(first names are a weak proxy for origin) and should be read as "what the
model defaults to", not as a claim about any individual story.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import lexicons as lx
from .features import matcher, split_sentences

ORIGIN_GROUPS = list(lx.NAME_ORIGINS)
_NAME_TO_ORIGIN: dict[str, str] = {}
for _group, _names in lx.NAME_ORIGINS.items():
    for _n in _names:
        _NAME_TO_ORIGIN.setdefault(_n, _group)

_TITLE_RE = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Miss|Professor|Captain|Officer|Nurse)\.?\s+([A-Z][a-z]+)")
_CAP_WORD = re.compile(r"\b([A-Z][a-zé'\-]{2,})\b")
_SENTENCE_STARTERS = {
    "The", "She", "He", "They", "It", "But", "And", "When", "Then", "There", "This", "That",
    "His", "Her", "Their", "Its", "In", "On", "At", "By", "For", "With", "From", "After",
    "Before", "As", "If", "So", "No", "Yes", "Not", "What", "Who", "Why", "How", "Where",
    "Every", "Some", "All", "Each", "Nobody", "Everyone", "Someone", "Once", "Now", "Later",
    "Outside", "Inside", "Still", "Just", "Even", "Only", "Maybe", "Perhaps", "Sure", "Okay",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January",
    "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "God", "Christmas", "Easter", "Ramadan", "Eid", "Diwali",
}


@dataclass
class Character:
    name: str
    mentions: int
    origin: str | None
    gender: str | None
    first_pos: int


@dataclass
class Demographics:
    characters: list[Character] = field(default_factory=list)
    protagonist: Character | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": [c.__dict__ for c in self.characters],
            "protagonist": self.protagonist.__dict__ if self.protagonist else None,
        }


# Names that are also common sentence-initial words ("Can you hear me?"): only a name mid-sentence.
_WORD_LIKE_NAMES = {"Can"}


def _at_sentence_start(text: str, pos: int) -> bool:
    before = text[:pos].rstrip(" \t\"'“”‘’(*_—-")
    return not before or before[-1] in ".!?:\n"


def _gender_of_name(name: str) -> str | None:
    if name in lx.MALE_NAMES and name not in lx.FEMALE_NAMES:
        return "male"
    if name in lx.FEMALE_NAMES and name not in lx.MALE_NAMES:
        return "female"
    return None


def _gender_from_context(text: str, name: str, others: set[str]) -> str | None:
    """Majority vote of pronoun cues in sentences that mention the name and no
    other named character (so the pronouns most likely refer to this one)."""
    m = matcher()
    votes: Counter = Counter()
    for _s, _e, sentence in split_sentences(text):
        if name not in sentence:
            continue
        if any(o != name and re.search(rf"\b{re.escape(o)}\b", sentence) for o in others):
            continue
        for _a, _b, term in m.spans("male", sentence):
            if term.lower() in ("he", "him", "his", "himself", "mr", "mr."):
                votes["male"] += 1
        for _a, _b, term in m.spans("female", sentence):
            if term.lower() in ("she", "her", "hers", "herself", "mrs", "mrs.", "ms", "ms."):
                votes["female"] += 1
    if not votes:
        return None
    (g1, n1), *rest = votes.most_common(2)
    if rest and rest[0][1] == n1:
        return None
    return g1


def analyze_demographics(text: str) -> Demographics:
    """Find named characters, their likely origin group and gender, and the protagonist
    (the most-mentioned name; ties go to the earliest)."""
    counts: Counter = Counter()
    first_pos: dict[str, int] = {}
    known = set(_NAME_TO_ORIGIN) | lx.MALE_NAMES | lx.FEMALE_NAMES
    prev_end = -1
    prev_known = False
    for m in _CAP_WORD.finditer(text):
        word = m.group(1)
        # "Anselm Duarte": a known name directly after another known name is a surname
        follows_name = prev_known and text[prev_end:m.start()] == " "
        is_known = word in known and not (word in _WORD_LIKE_NAMES and _at_sentence_start(text, m.start()))
        if is_known and not follows_name:
            counts[word] += 1
            first_pos.setdefault(word, m.start())
        prev_end, prev_known = m.end(), is_known
    # names after a title are characters even if we do not know the name
    for m in _TITLE_RE.finditer(text):
        word = m.group(1)
        if word not in _SENTENCE_STARTERS and word not in counts:
            counts[word] += len(re.findall(rf"\b{re.escape(word)}\b", text))
            first_pos.setdefault(word, m.start())
    characters = []
    names = set(counts)
    for name, n in counts.items():
        gender = _gender_of_name(name) or _gender_from_context(text, name, names)
        characters.append(Character(name=name, mentions=n, origin=_NAME_TO_ORIGIN.get(name),
                                    gender=gender, first_pos=first_pos[name]))
    characters.sort(key=lambda c: (-c.mentions, c.first_pos))
    return Demographics(characters=characters, protagonist=characters[0] if characters else None)


def summarize(stories: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate demographics over a list of story dicts (needs `text`)."""
    prot_gender: Counter = Counter()
    prot_origin: Counter = Counter()
    all_origin: Counter = Counter()
    all_gender: Counter = Counter()
    name_df: Counter = Counter()  # stories in which each name appears
    stories_with_non_western = 0
    n_with_names = 0
    for s in stories:
        d = analyze_demographics(s["text"])
        if not d.characters:
            continue
        n_with_names += 1
        name_df.update({c.name for c in d.characters})
        p = d.protagonist
        prot_gender[p.gender or "unknown"] += 1
        prot_origin[p.origin or "unknown"] += 1
        non_western = False
        for c in d.characters:
            all_origin[c.origin or "unknown"] += 1
            all_gender[c.gender or "unknown"] += 1
            if c.origin and c.origin != "anglo_western":
                non_western = True
        stories_with_non_western += int(non_western)

    def share(counter: Counter, keys: list[str]) -> dict[str, float]:
        total = sum(counter.values()) or 1
        return {k: round(counter[k] / total, 3) for k in keys}

    genders = ["male", "female", "unknown"]
    origins = ORIGIN_GROUPS + ["unknown"]
    return {
        "stories_with_named_characters": n_with_names,
        "protagonist_gender": share(prot_gender, genders),
        "protagonist_origin": share(prot_origin, origins),
        "all_characters_gender": share(all_gender, genders),
        "all_characters_origin": share(all_origin, origins),
        "share_stories_with_non_western_name": round(stories_with_non_western / max(1, n_with_names), 3),
        "character_count": sum(all_origin.values()),
        # name reuse: a model that keeps casting the same few names has a narrow default cast
        "distinct_names": len(name_df),
        "top_names": [{"name": n, "share": round(c / max(1, n_with_names), 3)} for n, c in name_df.most_common(5)],
    }
