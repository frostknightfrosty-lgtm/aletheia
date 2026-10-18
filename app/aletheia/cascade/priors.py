"""Base-rate priors for candidate matches (Phase 17, P17.4).

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.2 — "prior log-odds for
a candidate match scale with handle entropy and name rarity (a collision-prone
handle like ``frost`` starts lower than a high-entropy one), with per-platform
adjustments. Marked uncalibrated until the calibrator is trained."

Honest limits, stated up front:

- The constants here are provisional v1 reviewable numbers, not fitted
  values. ``PriorResult.calibrated`` is always ``False`` from this module.
- Name rarity needs a frequency table the project does not ship. Callers may
  pass one (folded token -> frequency in (0, 1]); without it the name term is
  ``0.0`` and the missing tokens are named in ``notes``.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from aletheia.cascade.matching import tokenize

__all__ = [
    "PriorResult",
    "candidate_prior",
    "handle_entropy_bits",
    "handle_prior_log_odds",
    "name_prior_log_odds",
    "shannon_bits",
]

# Provisional v1 constants (reviewable).
HANDLE_ENTROPY_SLOPE = 0.15  # log-odds per bit of handle entropy
HANDLE_ENTROPY_REFERENCE_BITS = 20.0  # entropy where the handle term is zero
NAME_RARITY_SCALE = 0.25  # log-odds per bit of (1 / token frequency)


@dataclass(frozen=True)
class PriorResult:
    """A prior log-odds contribution plus honesty metadata."""

    log_odds: float
    calibrated: bool = False
    notes: tuple[str, ...] = ()


def shannon_bits(value: str) -> float:
    """Total empirical entropy of the string: length x per-character entropy.

    ``"aaaa"`` is 0 bits (no surprise); a random 8-character string over a
    large alphabet is ~40 bits. This is the surprise of *this* string under
    its own character distribution — a cheap, transparent rarity proxy.
    """
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    per_char = 0.0
    for count in counts.values():
        probability = count / length
        per_char -= probability * math.log2(probability)
    return per_char * length


def handle_entropy_bits(handle: str) -> float:
    """Entropy of a handle with a leading ``@`` stripped (it carries no information)."""
    return shannon_bits(handle.strip().lstrip("@"))


def handle_prior_log_odds(
    handle: str,
    *,
    platform_adjustment: float = 0.0,
    entropy_slope: float = HANDLE_ENTROPY_SLOPE,
    reference_bits: float = HANDLE_ENTROPY_REFERENCE_BITS,
) -> PriorResult:
    """Prior log-odds from handle entropy, plus a caller platform adjustment."""
    entropy = handle_entropy_bits(handle)
    log_odds = entropy_slope * (entropy - reference_bits) + platform_adjustment
    return PriorResult(
        log_odds=log_odds,
        calibrated=False,
        notes=(
            "handle entropy prior is a provisional v1 constant, uncalibrated",
        ),
    )


def name_prior_log_odds(
    name: str,
    *,
    rarity: Mapping[str, float] | None,
    scale: float = NAME_RARITY_SCALE,
) -> PriorResult:
    """Prior log-odds from the rarest known name token.

    ``rarity`` maps folded tokens to population frequency in (0, 1]. The
    rarest known token governs (a distinctive surname says more than the
    given name); unknown tokens are listed in the notes.
    """
    tokens = tokenize(name)
    if rarity is None:
        return PriorResult(
            log_odds=0.0,
            calibrated=False,
            notes=("no name-rarity table supplied; name prior is 0.0",),
        )
    known: list[tuple[str, float]] = []
    missing: list[str] = []
    for token in tokens:
        frequency = rarity.get(token)
        if frequency is None or not (0.0 < frequency <= 1.0):
            missing.append(token)
            continue
        known.append((token, frequency))
    notes: list[str] = ["name rarity prior is uncalibrated"]
    if missing:
        notes.append(f"no rarity entry for: {', '.join(missing)}")
    if not known:
        return PriorResult(log_odds=0.0, calibrated=False, notes=tuple(notes))
    token, frequency = min(known, key=lambda item: item[1])
    log_odds = scale * (-math.log2(frequency))
    notes.append(f"rarest known token: {token}")
    return PriorResult(log_odds=log_odds, calibrated=False, notes=tuple(notes))


def candidate_prior(
    *,
    handles: Iterable[str] = (),
    names: Iterable[str] = (),
    rarity: Mapping[str, float] | None = None,
    platform_adjustment: float = 0.0,
) -> PriorResult:
    """Combined prior for one candidate: handle entropy + name rarity + platform.

    Each distinct handle contributes its entropy term; names contribute the
    rarest-token term once per distinct name; the platform adjustment is
    applied once.
    """
    total = 0.0
    notes: list[str] = []
    for handle in dict.fromkeys(handles):
        result = handle_prior_log_odds(handle)
        total += result.log_odds
        notes.extend(result.notes)
    for name in dict.fromkeys(names):
        result = name_prior_log_odds(name, rarity=rarity)
        total += result.log_odds
        notes.extend(result.notes)
    total += platform_adjustment
    return PriorResult(log_odds=total, calibrated=False, notes=tuple(notes))
