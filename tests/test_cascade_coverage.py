"""Tests for the coverage audit artifact (P17.8)."""

from __future__ import annotations

import pytest

from aletheia.cascade.coverage import CoverageAuditError, assert_coverage, build_coverage
from aletheia.core.models import SeedType


def test_coverage_ok():
    audit = build_coverage(
        expected_adapters=["github", "reddit"],
        ran_adapters=["github"],
        skips={"reddit": "requires REDDIT_CLIENT_ID"},
        pivot_proposals={SeedType.USERNAME: 2},
        gate_evaluations={SeedType.USERNAME: 2},
        egress={"total": 10, "allowed": 9, "refused": 1},
        run_id="r1",
    )
    assert audit.ok
    assert audit.payload["egress_included"] is True
    assert audit.payload["adapters"]["skipped"] == {"reddit": "requires REDDIT_CLIENT_ID"}
    assert audit.payload["pivot_types"]["username"] == {"proposed": 2, "gate_evaluations": 2}
    assert_coverage(audit)  # must not raise


def test_coverage_violations():
    audit = build_coverage(
        expected_adapters=["github", "reddit"],
        ran_adapters=["github"],
        pivot_proposals={SeedType.EMAIL: 3, SeedType.USERNAME: 1},
        gate_evaluations={SeedType.USERNAME: 1},
        egress={"total": 10, "allowed": 9, "refused": 2},
    )
    assert audit.payload["ok"] is False
    assert any("reddit" in violation for violation in audit.violations)
    assert any("email" in violation for violation in audit.violations)
    assert any("egress" in violation for violation in audit.violations)
    with pytest.raises(CoverageAuditError) as excinfo:
        assert_coverage(audit)
    assert excinfo.value.violations == audit.violations


def test_egress_without_full_telemetry_is_not_guessed():
    audit = build_coverage(expected_adapters=[], ran_adapters=[], egress={"total": 5})
    assert audit.payload["egress_included"] is False
    assert audit.payload["egress"] is None
    assert audit.ok


def test_coverage_is_deterministic():
    kwargs = dict(
        expected_adapters=["b", "a"],
        ran_adapters=["a"],
        pivot_proposals={SeedType.USERNAME: 1},
        gate_evaluations={SeedType.USERNAME: 1},
    )
    assert build_coverage(**kwargs).payload == build_coverage(**kwargs).payload
    assert build_coverage(**kwargs).payload["adapters"]["expected"] == ["a", "b"]
