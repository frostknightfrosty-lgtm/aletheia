"""Informational jurisdiction warnings.

This implements the project direction's sensitive-behavior requirement: when a
seed or a finding indicates a strong-privacy jurisdiction, a minor, health data,
or a protected-class context, the run records an informational warning. The
warnings never gate, block, or alter a run, and they are **not** a legal
determination: they are heuristic matches over the attributes a run happened to
collect, and both false positives and false negatives are expected. The signal
strings recorded here say exactly what matched, so an operator can re-check
every warning by hand.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from aletheia.core.models import Entity, Seed

WARNING_NOTE = (
    "Informational heuristic match, not a legal determination; "
    "verify against authoritative sources before relying on it."
)

KIND_PRIVACY_JURISDICTION = "strong_privacy_jurisdiction"
KIND_MINOR = "minor_indicators"
KIND_HEALTH_DATA = "health_data_indicators"
KIND_PROTECTED_CLASS = "protected_class_indicators"

# Strong-privacy jurisdictions: the EU/EEA member states plus the United
# Kingdom and Switzerland (GDPR / UK GDPR / FADP regimes). Full names match as
# substrings; two-letter codes match as tokens only. The list is a documented,
# static heuristic - it is not an ISO-3166 dataset.
PRIVACY_JURISDICTIONS: frozenset[str] = frozenset({
    "austria", "at", "belgium", "be", "bulgaria", "bg", "croatia", "hr",
    "cyprus", "cy", "czechia", "czech republic", "cz", "denmark", "dk",
    "estonia", "ee", "finland", "fi", "france", "fr", "germany", "de",
    "greece", "gr", "hungary", "hu", "ireland", "ie", "italy", "it",
    "latvia", "lv", "lithuania", "lt", "luxembourg", "lu", "malta", "mt",
    "netherlands", "the netherlands", "nl", "poland", "pl", "portugal", "pt",
    "romania", "ro", "slovakia", "sk", "slovenia", "si", "spain", "es",
    "sweden", "se", "iceland", "is", "liechtenstein", "li", "norway", "no",
    "united kingdom", "uk", "gb", "great britain", "england", "scotland",
    "wales", "northern ireland", "switzerland", "ch", "european union", "eu",
    "european economic area", "eea", "gdpr",
})

JURISDICTION_ATTRS = frozenset({
    "country", "country_code", "address_country", "location_country",
    "nationality", "jurisdiction",
})
HEALTH_ATTRS = frozenset({
    "health", "health_data", "medical", "medical_data", "diagnosis",
    "medication", "patient", "condition", "conditions",
})
PROTECTED_ATTRS = frozenset({
    "religion", "religious_affiliation", "faith", "ethnicity", "ethnic_group",
    "race", "racial_group", "sexual_orientation", "union_membership",
    "trade_union", "disability", "disabilities",
})
# Attributes whose *values* are scanned for topical keywords (industry/category
# style fields). Free-text values elsewhere are not scanned: the noise would
# make the signal meaningless.
TOPICAL_ATTRS = frozenset({"industry", "sector", "category", "topic", "record_type"})
HEALTH_KEYWORDS = ("health", "medical", "patient", "diagnosis", "clinic", "hospital", "medication", "therapy", "pharma")
PROTECTED_KEYWORDS = ("religion", "religious", "faith", "church", "mosque", "synagogue", "ethnic", "race", "racial", "lgbt", "sexual orientation", "trade union", "union member")


class JurisdictionWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    subject: str
    signal: str
    note: str = WARNING_NOTE

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _short(value: Any) -> str:
    rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return rendered if len(rendered) <= 120 else rendered[:117] + "..."


def _token_match(attr_value: str, keywords: frozenset[str]) -> bool:
    haystack = attr_value.casefold().strip()
    if not haystack:
        return False
    tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
    for keyword in keywords:
        if keyword in tokens:
            return True
        if len(keyword) > 3 and keyword in haystack:
            return True
    return False


def _compute_age(lowered: dict[str, Any]) -> int | None:
    try:
        age = int(lowered["age"])
    except (KeyError, TypeError, ValueError):
        age = None
    if age is not None and 0 <= age <= 130:
        return age
    today = datetime.now(timezone.utc).date()
    try:
        birth_year = int(lowered["birth_year"])
    except (KeyError, TypeError, ValueError):
        birth_year = None
    if birth_year is not None and 1900 <= birth_year <= today.year:
        return today.year - birth_year
    for key in ("birthdate", "birth_date", "dob"):
        raw = lowered.get(key)
        if not isinstance(raw, str):
            continue
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        computed = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
        if 0 <= computed <= 130:
            return computed
    return None


def evaluate_jurisdiction_warnings(
    *,
    seeds: Sequence[Seed] | None = None,
    entities: Iterable[Entity] | None = None,
) -> list[JurisdictionWarning]:
    """Return deduplicated informational warnings for a run's seeds and entities."""
    warnings: list[JurisdictionWarning] = []
    seen: set[tuple[str, str, str]] = set()

    def add(kind: str, subject: str, signal: str) -> None:
        key = (kind, subject, signal)
        if key in seen:
            return
        seen.add(key)
        warnings.append(JurisdictionWarning(kind=kind, subject=subject, signal=signal))

    for index, seed in enumerate(seeds or ()):
        if seed.value.casefold() in PRIVACY_JURISDICTIONS:
            add(KIND_PRIVACY_JURISDICTION, f"seed:{index}", f"seed:{seed.type}={seed.value}")

    for entity in entities or ():
        lowered = {str(key).casefold(): value for key, value in entity.attributes.items()}
        subject = f"entity:{entity.entity_type.value}={entity.canonical_value}"
        for key, value in lowered.items():
            values = value if isinstance(value, (list, tuple, set)) else [value]
            rendered_values = [item if isinstance(item, str) else json.dumps(item, sort_keys=True, default=str) for item in values]
            if key in JURISDICTION_ATTRS and any(_token_match(item, PRIVACY_JURISDICTIONS) for item in rendered_values):
                add(KIND_PRIVACY_JURISDICTION, subject, f"attribute:{key}={_short(value)}")
            if key in HEALTH_ATTRS:
                add(KIND_HEALTH_DATA, subject, f"attribute:{key}={_short(value)}")
            if key in PROTECTED_ATTRS:
                add(KIND_PROTECTED_CLASS, subject, f"attribute:{key}={_short(value)}")
            if key in TOPICAL_ATTRS:
                haystack = " ".join(rendered_values).casefold()
                if any(keyword in haystack for keyword in HEALTH_KEYWORDS):
                    add(KIND_HEALTH_DATA, subject, f"attribute:{key}={_short(value)}")
                if any(keyword in haystack for keyword in PROTECTED_KEYWORDS):
                    add(KIND_PROTECTED_CLASS, subject, f"attribute:{key}={_short(value)}")
        if lowered.get("minor") is True or lowered.get("is_minor") is True:
            add(KIND_MINOR, subject, "attribute:minor=true")
        age = _compute_age(lowered)
        if age is not None and age < 18:
            add(KIND_MINOR, subject, f"computed_age={age}")

    return warnings
