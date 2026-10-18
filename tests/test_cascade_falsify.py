"""Tests for the falsification-first review pass (P17.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from aletheia.cascade.claims import Claim
from aletheia.cascade.falsify import CONFLICTING_ATTRIBUTE_KEYS, falsify
from aletheia.cascade.scoring import EvidenceClass
from aletheia.core.models import EntityType


def _claim(
    entity_type: EntityType,
    value: str,
    *,
    adapter: str = "tool",
    seed_index: int | None = None,
    attributes: dict | None = None,
) -> Claim:
    return Claim(
        type=entity_type,
        value=value,
        source_adapter=adapter,
        confidence=1.0,
        finding_id=uuid4(),
        seed_index=seed_index,
        attributes=attributes or {},
    )


def test_conflicting_names_produce_veto():
    result = falsify(
        [_claim(EntityType.NAME, "Robert Smith")],
        [_claim(EntityType.NAME, "Zbigniew Brzezinski")],
    )
    assert [item.evidence_class for item in result.vetoes] == [EvidenceClass.VETO]
    assert "conflicting name-class claims" in result.vetoes[0].reason
    assert result.warnings == ()
    assert result.strongest_disconfirming is not None
    assert result.strongest_disconfirming.startswith("conflicting name-class claims")
    assert "cross-claim veto sweep" in result.probes_run


def test_conflicting_vin_produces_veto():
    result = falsify(
        [_claim(EntityType.TRANSPORT_ASSET_RECORD, "1HGCM82633A004352")],
        [_claim(EntityType.TRANSPORT_ASSET_RECORD, "5YJ3E1EA7KF317000")],
    )
    assert [item.evidence_class for item in result.vetoes] == [EvidenceClass.VETO]
    assert result.vetoes[0].reason == "conflicting vin"


def test_attribute_contradictions_and_matching_values():
    conflict = falsify(
        [_claim(EntityType.PERSON, "Alice", attributes={"date_of_birth": "1988-01-02"})],
        [_claim(EntityType.PERSON, "Alice", attributes={"date_of_birth": "1989-03-04"})],
    )
    assert [item.reason for item in conflict.vetoes] == ["conflicting date_of_birth"]
    matching = falsify(
        [_claim(EntityType.PERSON, "Alice", attributes={"national_id": "X123"})],
        [_claim(EntityType.PERSON, "Alice", attributes={"national_id": "x123"})],
    )
    assert matching.vetoes == ()
    assert "national_id" in CONFLICTING_ATTRIBUTE_KEYS
    # Non-string attribute values are not comparable and are ignored.
    ignored = falsify(
        [_claim(EntityType.PERSON, "Alice", attributes={"date_of_birth": 19880102})],
        [_claim(EntityType.PERSON, "Alice", attributes={"date_of_birth": 19890304})],
    )
    assert ignored.vetoes == ()


def test_identical_claims_do_not_veto():
    result = falsify(
        [_claim(EntityType.EMAIL, "alice@example.com")],
        [_claim(EntityType.EMAIL, "alice@example.com")],
    )
    assert result.vetoes == ()
    assert result.warnings == ()
    assert result.strongest_disconfirming is None
    assert result.probes_run == ("cross-claim veto sweep", "attribute contradictions")


def test_dedupes_by_reason_and_origin():
    def name_claims(values: list[str], adapter: str, seed_index: int) -> list[Claim]:
        return [
            _claim(EntityType.NAME, value, adapter=adapter, seed_index=seed_index)
            for value in values
        ]

    result = falsify(
        name_claims(["Robert Smith", "Robert Smith"], "a", 0),
        name_claims(["Zbigniew Brzezinski", "Zbigniew Brzezinski"], "b", 1),
    )
    assert len(result.vetoes) == 1


def test_disjoint_eras_warn_but_never_veto():
    left_era = (
        datetime(2015, 1, 1, tzinfo=timezone.utc),
        datetime(2016, 1, 1, tzinfo=timezone.utc),
    )
    right_era = (
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    result = falsify(
        [_claim(EntityType.USERNAME, "alice")],
        [_claim(EntityType.USERNAME, "alice")],
        left_era=left_era,
        right_era=right_era,
    )
    assert result.vetoes == ()
    assert len(result.warnings) == 1
    assert "disjoint activity eras" in result.warnings[0]
    assert "era coherence" in result.probes_run
    assert result.strongest_disconfirming == result.warnings[0]


def test_overlapping_eras_no_warning():
    left_era = (
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    right_era = (
        datetime(2020, 6, 1, tzinfo=timezone.utc),
        datetime(2021, 6, 1, tzinfo=timezone.utc),
    )
    result = falsify(
        [_claim(EntityType.USERNAME, "alice")],
        [_claim(EntityType.USERNAME, "alice")],
        left_era=left_era,
        right_era=right_era,
    )
    assert result.warnings == ()
    assert "era coherence" in result.probes_run
