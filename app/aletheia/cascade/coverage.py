"""Coverage audit artifact (P17.8).

Design of record: ``docs/PIVOT_CASCADE.md`` section 12 — "end-of-run assertion
that every matching adapter ran or has a skip reason, every pivot type had a
gate evaluation, and egress accounting balances — the 'did we really squeeze
it' proof".

All inputs are explicit collections the engine already has; the audit reports
only what it was given. Absent egress telemetry is marked
``egress_included: false`` and never guessed; when telemetry is present it must
carry ``{"total", "allowed", "refused"}`` and balance exactly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aletheia.core.models import SeedType

__all__ = ["CoverageAudit", "CoverageAuditError", "assert_coverage", "build_coverage"]


class CoverageAuditError(ValueError):
    """Raised by :func:`assert_coverage` when the audit has violations."""

    def __init__(self, violations: Sequence[str]) -> None:
        self.violations = tuple(violations)
        super().__init__("coverage audit failed: " + "; ".join(self.violations))


@dataclass(frozen=True)
class CoverageAudit:
    payload: dict[str, Any]
    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations


def build_coverage(
    *,
    expected_adapters: Sequence[str],
    ran_adapters: Sequence[str],
    skips: Mapping[str, str] | None = None,
    pivot_proposals: Mapping[SeedType, int] | None = None,
    gate_evaluations: Mapping[SeedType, int] | None = None,
    egress: Mapping[str, int] | None = None,
    run_id: str | None = None,
) -> CoverageAudit:
    """Build the coverage payload and its violation list, deterministically."""
    expected = sorted(set(expected_adapters))
    ran = sorted(set(ran_adapters))
    skip_map = {str(source): str(reason) for source, reason in (skips or {}).items()}
    proposals = {seed_type: int(count) for seed_type, count in (pivot_proposals or {}).items()}
    gates = {seed_type: int(count) for seed_type, count in (gate_evaluations or {}).items()}
    violations: list[str] = []
    for adapter in expected:
        if adapter not in ran and adapter not in skip_map:
            violations.append(
                f"adapter {adapter!r} matched but neither ran nor has a skip reason"
            )
    for seed_type in sorted(proposals):
        if proposals[seed_type] > 0 and gates.get(seed_type, 0) < proposals[seed_type]:
            violations.append(
                f"pivot type {seed_type.value!r}: {proposals[seed_type]} proposed, "
                f"{gates.get(seed_type, 0)} gate evaluations"
            )
    egress_payload: dict[str, int] | None = None
    egress_included = egress is not None and {"total", "allowed", "refused"} <= set(egress)
    if egress_included:
        egress_payload = {str(key): int(value) for key, value in egress.items()}
        if egress_payload["allowed"] + egress_payload["refused"] != egress_payload["total"]:
            violations.append(
                "egress accounting does not balance: "
                f"{egress_payload['allowed']} + {egress_payload['refused']} "
                f"!= {egress_payload['total']}"
            )
    payload = {
        "coverage_version": 1,
        "run_id": run_id,
        "adapters": {
            "expected": expected,
            "ran": ran,
            "skipped": {source: skip_map[source] for source in sorted(skip_map)},
        },
        "pivot_types": {
            seed_type.value: {
                "proposed": proposals[seed_type],
                "gate_evaluations": gates.get(seed_type, 0),
            }
            for seed_type in sorted(proposals)
        },
        "egress": egress_payload,
        "egress_included": bool(egress_included),
        "violations": violations,
        "ok": not violations,
    }
    return CoverageAudit(payload=payload, violations=tuple(violations))


def assert_coverage(audit: CoverageAudit) -> None:
    """The design's end-of-run assertion: raise on any violation."""
    if not audit.ok:
        raise CoverageAuditError(audit.violations)
