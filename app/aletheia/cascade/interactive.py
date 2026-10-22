"""Interactive candidate labelling for the cascade (Phase 18.1).

The engine never prompts by itself. It accepts an injected ``review_callback``
and asks it only for a ``SAME_AS_CANDIDATE`` pair whose base confidence falls
in the review band. This module supplies the CLI-friendly implementation of
that callback plus the calibration-fixture append used to keep the operator's
labels.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aletheia.cascade.claims import Claim

__all__ = [
    "CANDIDATE_REVIEW_MIN",
    "CANDIDATE_REVIEW_MAX",
    "DEFAULT_CALIBRATION_PAIRS_PATH",
    "CandidateMatch",
    "append_calibration_pair",
    "default_calibration_pairs_path",
    "format_candidate_prompt",
    "prompt_candidate",
]

CANDIDATE_REVIEW_MIN = 0.70
CANDIDATE_REVIEW_MAX = 0.85
DEFAULT_CALIBRATION_PAIRS_PATH = "tests/fixtures/calibration_pairs.json"


def default_calibration_pairs_path() -> Path:
    """The repo fixture when running from source, else the relative default."""
    root = Path(__file__).resolve().parents[3]
    candidate = root / "tests" / "fixtures" / "calibration_pairs.json"
    return candidate if candidate.exists() else Path(DEFAULT_CALIBRATION_PAIRS_PATH)


_PLATFORM_LABELS = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "reddit": "Reddit",
    "youtube": "YouTube",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "linkedin": "LinkedIn",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
    "x": "X",
    "twitter": "Twitter",
}


def _claim_platform(claim: Claim) -> str:
    attributes = {
        str(key).casefold(): value for key, value in (claim.attributes or {}).items()
    }
    raw = attributes.get("platform") or attributes.get("service") or attributes.get("site")
    if isinstance(raw, str) and raw.strip():
        key = raw.strip().casefold().replace("_", "").replace("-", "")
        if key in _PLATFORM_LABELS:
            return _PLATFORM_LABELS[key]
        return raw.strip().replace("-", " ").title()
    if claim.source_adapter:
        key = claim.source_adapter.casefold().replace("_", "").replace("-", "")
        if key in _PLATFORM_LABELS:
            return _PLATFORM_LABELS[key]
        return claim.source_adapter.replace("_", " ").replace("-", " ").title()
    return "Unknown"


def _claim_handle(claim: Claim) -> str:
    attributes = {
        str(key).casefold(): value for key, value in (claim.attributes or {}).items()
    }
    for key in ("username", "login", "handle", "screen_name", "user"):
        value = attributes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return claim.value


@dataclass(frozen=True)
class CandidateMatch:
    """One SAME_AS_CANDIDATE edge presented to the operator."""

    subject_claim: Claim
    candidate_claim: Claim
    confidence: float
    score: float = 0.0
    reason: str = ""

    @property
    def left_value(self) -> str:
        return _claim_handle(self.subject_claim)

    @property
    def right_value(self) -> str:
        return _claim_handle(self.candidate_claim)

    @property
    def left_platform(self) -> str:
        return _claim_platform(self.subject_claim)

    @property
    def right_platform(self) -> str:
        return _claim_platform(self.candidate_claim)

    def prompt(self) -> str:
        return format_candidate_prompt(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_value": self.left_value,
            "left_platform": self.left_platform,
            "right_value": self.right_value,
            "right_platform": self.right_platform,
            "confidence": self.confidence,
            "score": self.score,
            "reason": self.reason,
        }


def format_candidate_prompt(match: CandidateMatch) -> str:
    """The operator-facing prompt, verbatim as specified for Phase 18.1."""
    return (
        f'[?] Candidate Match: "{match.left_value}" ({match.left_platform}) == '
        f'"{match.right_value}" ({match.right_platform}). Are they the same person? '
        "[y/N/s(kip)]"
    )


ReviewCallback = Callable[[CandidateMatch], str]


def prompt_candidate(
    match: CandidateMatch,
    *,
    input_func: Callable[[str], str] | None = None,
    output_func: Callable[[str], Any] | None = None,
) -> str:
    """Ask the operator; return ``confirmed``, ``excluded``, or ``skip``.

    ``input_func``/``output_func`` are resolved at call time, so a CLI test
    (or an embedding application) can replace ``builtins.input`` normally.
    """
    ask = input_func or input
    say = output_func or print
    while True:
        answer = ask(match.prompt()).strip().casefold()
        if answer in {"y", "yes"}:
            return "confirmed"
        if answer in {"n", "no"}:
            return "excluded"
        if answer in {"", "s", "skip"}:
            return "skip"
        say("Please answer y, n, or s.")


def append_calibration_pair(
    path: str | Path,
    *,
    score: float,
    label: int,
    note: str,
    left: str = "",
    right: str = "",
    source: str = "cascade_interactive",
) -> dict[str, Any]:
    """Append one human-labelled pair without changing the fixture schema.

    Existing entries keep their ``score``/``label``/``note`` shape; the extra
    context fields are additive and ignored by the calibrator loader.
    """
    if label not in (0, 1):
        raise ValueError("label must be 0 or 1")
    target = Path(path)
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("pairs"), list):
            raise ValueError(f"{target} is not a calibration-pairs document")
    else:
        payload = {"description": "Human-labelled cascade candidate pairs.", "pairs": []}
    entry: dict[str, Any] = {
        "score": round(float(score), 6),
        "label": int(label),
        "note": note,
        "left": left,
        "right": right,
        "source": source,
        "labeled_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["pairs"].append(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entry


def interactive_reviewer(
    calibration_pairs_path: str | Path,
    *,
    input_func: Callable[[str], str] | None = None,
    output_func: Callable[[str], Any] | None = None,
) -> tuple[ReviewCallback, list[dict[str, Any]]]:
    """Build a reviewer and a mutable list of recorded labels for one run."""
    recorded: list[dict[str, Any]] = []

    def review(match: CandidateMatch) -> str:
        decision = prompt_candidate(
            match, input_func=input_func, output_func=output_func
        )
        if decision == "skip":
            return decision
        label = 1 if decision == "confirmed" else 0
        note = (
            "human-labeled cascade candidate: "
            f'"{match.left_value}" ({match.left_platform}) == '
            f'"{match.right_value}" ({match.right_platform})'
        )
        recorded.append(
            append_calibration_pair(
                calibration_pairs_path,
                score=match.confidence,
                label=label,
                note=note,
                left=match.left_value,
                right=match.right_value,
                source="cascade_interactive",
            )
        )
        return decision

    return review, recorded
