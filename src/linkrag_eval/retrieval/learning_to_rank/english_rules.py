"""Basic English lexical rules, not negation scope or entity/relationship analysis."""

from __future__ import annotations

import re

RULES_VERSION = "english_basic_v1"
APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})
NEGATORS = ("not", "no", "never", "neither", "nor", "without")
NEGATIVE_CONTRACTIONS = (
    "isn't", "aren't", "wasn't", "weren't", "don't", "doesn't", "didn't",
    "hasn't", "haven't", "hadn't", "can't", "couldn't", "won't", "wouldn't",
    "shouldn't", "mustn't", "needn't", "daren't", "shan't", "oughtn't",
)
_NEGATION_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(t) for t in (*NEGATORS, "cannot", *NEGATIVE_CONTRACTIONS))
    + r")(?!\w)", re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_GROUPED_NUMBER_RE = re.compile(r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\w|\.\d|,\d)")
_ABBREVIATION_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc)\.|\b(?:[a-z]\.){2,}", re.IGNORECASE,
)
_INITIAL_RE = re.compile(r"\b[A-Z]\.(?=\s+[A-Z])")
_ENGLISH_SEPARATOR_RE = re.compile(r"\.|\b(?:and|but|if)\b", re.IGNORECASE)


def negations(text: str) -> set[str]:
    """Canonicalize cannot and declared n't contractions to not; keep other tokens distinct."""
    tokens = {m.group().lower() for m in _NEGATION_RE.finditer(text.translate(APOSTROPHES))}
    return {"not" if t == "cannot" or t in NEGATIVE_CONTRACTIONS else t for t in tokens}


def numbers(text: str) -> set[str]:
    """Preserve decimal/grouped tokens; compare extracted tokens rather than substrings."""
    return {m.group().replace(",", "") for m in _NUMBER_RE.finditer(text)}


def identifiers(text: str, pattern: re.Pattern) -> set[str]:
    normalized = _GROUPED_NUMBER_RE.sub(lambda m: m.group().replace(",", ""), text)
    return {m.group().lower().rstrip("._-") for m in pattern.finditer(normalized)}


def clauses(text: str, legacy_separators: re.Pattern) -> list[str]:
    """Surface clauses: punctuation plus and/but/if, protecting numeric dots/commas and abbreviations.

    The finite abbreviation list is conservative, not a sentence parser. It can
    miss a sentence boundary after an abbreviation; no semantic-scope claim.
    """
    protected = set()
    for pattern in (_GROUPED_NUMBER_RE, _ABBREVIATION_RE, _INITIAL_RE):
        for match in pattern.finditer(text):
            protected.update(i for i in range(*match.span()) if text[i] in ".,")
    protected.update(i for i in range(1, len(text) - 1)
                     if text[i] == "." and text[i-1].isdigit() and text[i+1].isdigit())
    spans = sorted({m.span() for pattern in (legacy_separators, _ENGLISH_SEPARATOR_RE)
                    for m in pattern.finditer(text) if m.start() not in protected})
    parts, start = [], 0
    for left, right in spans:
        if left < start:
            continue
        parts.append(text[start:left].strip())
        start = right
    parts.append(text[start:].strip())
    return [part for part in parts if len(part) >= 2]
