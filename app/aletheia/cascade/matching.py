"""Pure matchers for the evidence engine (Phase 17, P17.4).

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.1.

- **String**: Jaro-Winkler and Levenshtein via ``rapidfuzz`` (already a
  project dependency, same as ``aletheia.phase2.resolution``), token-set
  ratio, IDF-weighted token overlap, Soundex phonetic keys (pure stdlib,
  verified against the published NARA vectors), common-English nickname
  expansion, diacritic folding and a small documented Cyrillic
  transliteration.
- **Graph**: set overlap helpers for declared/outbound link sets
  (mutual-link detection is the intersection; the caller reads it as HARD
  only when both accounts explicitly declare each other).
- **Temporal**: activity-window overlap and exponential recency decay.

Everything here is a pure function over plain values: no cascade models, no
I/O, no network. Similarity *thresholds* live in the evidence mapping
(``aletheia.cascade.evidence``) so they stay reviewable in one place.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import AbstractSet, Mapping

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler, Levenshtein

__all__ = [
    "era_coherence",
    "fold_diacritics",
    "idf_token_overlap",
    "jaccard_similarity",
    "jaro_winkler",
    "levenshtein_similarity",
    "mutual_link_overlap",
    "name_variants",
    "names_equivalent",
    "overlap_ratio",
    "phonetic_key",
    "recency_decay",
    "set_overlap",
    "shared_values",
    "soundex",
    "token_set_ratio",
    "tokenize",
    "transliterate",
]

# Common English nickname families (curated, deliberately not exhaustive:
# the table is data, extend it as calibration data arrives).
_NICKNAMES: dict[str, frozenset[str]] = {
    "alexander": frozenset({"alex", "sasha", "xander"}),
    "andrew": frozenset({"andy", "drew"}),
    "anthony": frozenset({"tony"}),
    "benjamin": frozenset({"ben", "benny"}),
    "catherine": frozenset({"kate", "katie", "kathy", "cathy", "kat"}),
    "charles": frozenset({"charlie", "chuck"}),
    "christopher": frozenset({"chris"}),
    "daniel": frozenset({"dan", "danny"}),
    "david": frozenset({"dave", "davey"}),
    "deborah": frozenset({"deb", "debbie"}),
    "edward": frozenset({"ed", "eddie", "ted"}),
    "elizabeth": frozenset({"liz", "lizzy", "beth", "betty", "eliza"}),
    "frances": frozenset({"fran", "franny"}),
    "gregory": frozenset({"greg"}),
    "henry": frozenset({"hank", "harry"}),
    "james": frozenset({"jim", "jimmy", "jamie"}),
    "jeffrey": frozenset({"jeff"}),
    "jennifer": frozenset({"jen", "jenny"}),
    "jessica": frozenset({"jess"}),
    "john": frozenset({"jack", "johnny"}),
    "joseph": frozenset({"joe", "joey"}),
    "katherine": frozenset({"kate", "katie", "kathy", "kat"}),
    "lawrence": frozenset({"larry"}),
    "margaret": frozenset({"maggie", "peggy", "meg"}),
    "matthew": frozenset({"matt"}),
    "michael": frozenset({"mike", "mikey"}),
    "nicholas": frozenset({"nick", "nicky"}),
    "patricia": frozenset({"pat", "patty", "tricia"}),
    "raymond": frozenset({"ray"}),
    "richard": frozenset({"rich", "richie", "dick"}),
    "robert": frozenset({"bob", "rob", "bobby", "robbie"}),
    "samuel": frozenset({"sam", "sammy"}),
    "stephen": frozenset({"steve", "stevie"}),
    "steven": frozenset({"steve", "stevie"}),
    "susan": frozenset({"sue", "susie"}),
    "theodore": frozenset({"ted", "teddy"}),
    "thomas": frozenset({"tom", "tommy"}),
    "timothy": frozenset({"tim"}),
    "william": frozenset({"will", "bill", "billy", "liam"}),
}

# Variant -> canonical families, built once.
_VARIANT_TO_CANONICAL: dict[str, str] = {}
for _canonical, _variants in _NICKNAMES.items():
    _VARIANT_TO_CANONICAL.setdefault(_canonical, _canonical)
    for _variant in _variants:
        _VARIANT_TO_CANONICAL.setdefault(_variant, _canonical)

_CYRILLIC: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_APOSTROPHES = {"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\u0060": "'"}
_INVISIBLES = {"\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": ""}

_SOUNDEX_CODES: dict[str, str] = {}
for _letters, _code in (
    ("BFPV", "1"),
    ("CGJKQSXZ", "2"),
    ("DT", "3"),
    ("L", "4"),
    ("MN", "5"),
    ("R", "6"),
):
    for _letter in _letters:
        _SOUNDEX_CODES[_letter] = _code


def fold_diacritics(value: str) -> str:
    """Casefolded text with diacritics stripped and typographic noise normalized."""
    for source, target in _APOSTROPHES.items():
        value = value.replace(source, target)
    for source, target in _INVISIBLES.items():
        value = value.replace(source, target)
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def transliterate(value: str) -> str:
    """Fold diacritics, then map Cyrillic to a documented Latin form."""
    folded = fold_diacritics(value)
    return "".join(_CYRILLIC.get(ch, ch) for ch in folded)


def jaro_winkler(left: str, right: str) -> float:
    """Normalized Jaro-Winkler similarity in [0, 1]."""
    return float(JaroWinkler.normalized_similarity(left, right))


def levenshtein_similarity(left: str, right: str) -> float:
    """Normalized Levenshtein similarity in [0, 1]."""
    return float(Levenshtein.normalized_similarity(left, right))


def token_set_ratio(left: str, right: str) -> float:
    """rapidfuzz token-set ratio, normalized to [0, 1]."""
    return float(fuzz.token_set_ratio(left, right)) / 100.0


def tokenize(value: str) -> list[str]:
    """Folded alphanumeric tokens (apostrophes kept inside words)."""
    folded = fold_diacritics(value)
    tokens: list[str] = []
    current: list[str] = []
    for ch in folded:
        if ch.isalnum() or ch == "'":
            current.append(ch)
        elif current:
            tokens.append("".join(current).strip("'"))
            current = []
    if current:
        tokens.append("".join(current).strip("'"))
    return [token for token in tokens if token]


def idf_token_overlap(
    left: str,
    right: str,
    idf: Mapping[str, float],
    *,
    default_idf: float = 1.0,
) -> float:
    """IDF-weighted Jaccard over folded tokens.

    ``idf`` maps a token to its inverse-document-frequency weight; unknown
    tokens get ``default_idf`` (rare tokens therefore dominate the overlap,
    which is the point: matching on "frost2233" says more than on "john").
    """
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens and not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    intersection = left_tokens & right_tokens
    union_weight = sum(idf.get(token, default_idf) for token in union)
    if union_weight == 0.0:
        return 0.0
    shared_weight = sum(idf.get(token, default_idf) for token in intersection)
    return shared_weight / union_weight


def soundex(name: str) -> str:
    """Standard Soundex key (NARA vectors: Robert->R163, Pfister->P236)."""
    letters = [ch for ch in name.upper() if "A" <= ch <= "Z"]
    if not letters:
        return ""
    first = letters[0]
    previous = _SOUNDEX_CODES.get(first, "0")
    digits: list[str] = []
    for ch in letters[1:]:
        if ch in "HW":
            continue  # not coded, and they do not reset
        if ch in "AEIOUY":
            previous = "0"
            continue
        code = _SOUNDEX_CODES.get(ch, "0")
        if code != "0" and code != previous:
            digits.append(code)
        previous = code
    return first + "".join(digits)[:3].ljust(3, "0")


def phonetic_key(name: str) -> str:
    """The v1 phonetic key. Soundex is the stdlib Soundex/Metaphone-class key;
    a double-metaphone backend is a documented later refinement."""
    return soundex(fold_diacritics(name))


def name_variants(name: str) -> frozenset[str]:
    """Folded name plus nickname-expansion combinations (full-string variants).

    "Robert Smith" yields {"robert smith", "bob smith", "rob smith", ...}.
    The table is curated, not exhaustive; unknown tokens pass through.
    """
    folded_tokens = tokenize(name)
    if not folded_tokens:
        return frozenset()
    per_token: list[list[str]] = []
    for token in folded_tokens:
        canonical = _VARIANT_TO_CANONICAL.get(token)
        if canonical is None:
            per_token.append([token])
        else:
            options = {canonical, token} | set(_NICKNAMES.get(canonical, ()))
            per_token.append(sorted(options))
    variants = [""]
    for options in per_token:
        variants = [f"{prefix} {option}".strip() for prefix in variants for option in options]
    return frozenset(variants)


def names_equivalent(left: str, right: str) -> bool:
    """True when two names share any nickname-expanded full-string variant."""
    left_variants = name_variants(left)
    right_variants = name_variants(right)
    if not left_variants or not right_variants:
        return False
    return not left_variants.isdisjoint(right_variants)


def set_overlap(left: AbstractSet[str], right: AbstractSet[str]) -> float:
    """Jaccard overlap of two value sets (0.0 when both are empty)."""
    if not left and not right:
        return 0.0
    union = set(left) | set(right)
    if not union:
        return 0.0
    return len(set(left) & set(right)) / len(union)


def jaccard_similarity(left: AbstractSet[str], right: AbstractSet[str]) -> float:
    """Explicit name for the Jaccard set similarity used by network matching."""
    return set_overlap(left, right)


def shared_values(left: AbstractSet[str], right: AbstractSet[str]) -> frozenset[str]:
    """The intersection of two declared-value sets."""
    return frozenset(set(left) & set(right))


def mutual_link_overlap(
    left_links: AbstractSet[str],
    right_links: AbstractSet[str],
) -> frozenset[str]:
    """Links both sides declare.

    Reading note: this is *shared outbound links*. A caller may label it
    "mutual declared links" only when each shared link is a link to the other
    account; otherwise it is the weaker "shared outbound link set".
    """
    return shared_values(left_links, right_links)


def overlap_ratio(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> float:
    """Overlap of two activity windows, relative to the shorter window.

    ``0.0`` when the windows do not overlap; both datetimes must be aware.
    """
    latest_start = max(left_start, right_start)
    earliest_end = min(left_end, right_end)
    if earliest_end <= latest_start:
        return 0.0
    overlap = (earliest_end - latest_start).total_seconds()
    shorter = min(
        (left_end - left_start).total_seconds(),
        (right_end - right_start).total_seconds(),
    )
    if shorter <= 0:
        return 0.0
    return min(1.0, overlap / shorter)


def era_coherence(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    """True when the two account eras share any active time at all."""
    return overlap_ratio(left_start, left_end, right_start, right_end) > 0.0


def recency_decay(
    observed_at: datetime,
    reference: datetime,
    half_life_days: float = 365.0,
) -> float:
    """Exponential decay weight in (0, 1]; future stamps clamp to 1.0."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    age_days = (reference - observed_at).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)
