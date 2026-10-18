"""Tests for the claim layer: normalization, dedup, strong keys, blocking.

Pure logic, no Docker, no network.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aletheia.cascade.claims import (
    Claim,
    block_claims,
    claim_from_finding,
    dedupe_claims,
    normalize_claim_value,
    strong_keys,
)
from aletheia.core.models import EntityType, Finding, Provenance


def _finding(entity_type: EntityType, value: str, **provenance_kwargs) -> Finding:
    return Finding(
        entity_type=entity_type,
        value=value,
        provenance=Provenance(
            tool="fixture_adapter",
            confidence=0.8,
            adapter_version="v1",
            **provenance_kwargs,
        ),
    )


def _claim(entity_type: EntityType, value: str, **overrides) -> Claim:
    data = {
        "type": entity_type,
        "value": value,
        "source_adapter": "fixture_adapter",
        "confidence": 0.8,
        "finding_id": uuid4(),
    }
    data.update(overrides)
    return Claim(**data)


def test_claim_from_finding_carries_provenance_and_normalizes():
    parent = uuid4()
    finding = _finding(
        EntityType.EMAIL,
        "Alice@Example.COM",
        source_url="https://evidence.test/x",
        seed_index=2,
        parent_finding_id=parent,
        raw_evidence_sha256="a" * 64,
    )
    claim = claim_from_finding(finding)
    assert claim.type is EntityType.EMAIL
    assert claim.value == "alice@example.com"
    assert claim.source_adapter == "fixture_adapter"
    assert claim.source_url == "https://evidence.test/x"
    assert claim.seed_index == 2
    assert claim.parent_finding_id == parent
    assert claim.finding_id == finding.finding_id
    assert claim.raw_evidence_sha256 == "a" * 64
    assert claim.source_grade.label == "F6"


def test_normalize_claim_value_per_type():
    assert normalize_claim_value(EntityType.EMAIL, "Alice@Example.COM") == "alice@example.com"
    assert (
        normalize_claim_value(EntityType.URL, "HTTPS://Example.COM/x#frag")
        == "https://example.com/x"
    )
    assert normalize_claim_value(EntityType.DOMAIN, "Example.COM.") == "example.com"
    assert normalize_claim_value(EntityType.USERNAME, "@Frost2233") == "frost2233"
    assert normalize_claim_value(EntityType.IP, "8.8.8.8") == "8.8.8.8"
    assert normalize_claim_value(EntityType.PHONE, "+1 (555) 123-4567") == "+15551234567"
    assert normalize_claim_value(EntityType.HOST, "Example.COM:443") == "example.com"
    assert normalize_claim_value(EntityType.NAME, "Alice   von  Example") == "Alice von Example"


def test_dedupe_claims_keeps_first_appearance():
    first = _claim(EntityType.DOMAIN, "example.com")
    second = _claim(EntityType.DOMAIN, "example.com")
    other = _claim(EntityType.DOMAIN, "other.example")
    assert dedupe_claims([first, second, other]) == [first, other]


def test_strong_keys_by_type():
    assert strong_keys(_claim(EntityType.EMAIL, "alice@example.com")) == {
        "email:alice@example.com"
    }
    assert strong_keys(_claim(EntityType.PHONE, "+15551234567")) == {"phone:+15551234567"}
    assert strong_keys(_claim(EntityType.DOMAIN, "example.com")) == {"domain:example.com"}
    assert strong_keys(_claim(EntityType.HOST, "example.com")) == {"domain:example.com"}
    assert strong_keys(_claim(EntityType.HOST, "8.8.8.8")) == set()
    assert strong_keys(_claim(EntityType.URL, "https://example.com/u/a")) == {
        "domain:example.com"
    }
    assert strong_keys(_claim(EntityType.USERNAME, "frost2233")) == {"username:frost2233"}
    assert strong_keys(_claim(EntityType.SOCIAL_ACCOUNT, "@frost2233")) == {
        "username:frost2233"
    }
    assert strong_keys(_claim(EntityType.SOCIAL_ACCOUNT, "https://github.com/frost2233")) == set()
    assert strong_keys(_claim(EntityType.EMAIL_AUTH_RECORD, "example.com")) == {
        "domain:example.com"
    }
    assert strong_keys(_claim(EntityType.TECHNICAL_FINDING, "contact: a@b.com")) == set()


def test_block_claims_pairs_within_shared_keys_only():
    shared = [
        _claim(EntityType.DOMAIN, "example.com"),
        _claim(EntityType.URL, "https://example.com/a"),
    ]
    lonely = _claim(EntityType.DOMAIN, "other.example")
    result = block_claims(shared + [lonely])
    assert result.blocks["domain:example.com"] == (shared[0].claim_id, shared[1].claim_id)
    assert len(result.pairs) == 1
    assert set(result.pairs[0]) == {shared[0].claim_id, shared[1].claim_id}
    assert result.oversized_blocks == ()


def test_block_claims_is_deterministic():
    claims = [
        _claim(EntityType.URL, "https://example.com/a"),
        _claim(EntityType.DOMAIN, "example.com"),
        _claim(EntityType.HOST, "example.com"),
    ]
    first = block_claims(claims)
    second = block_claims(claims)
    assert first == second
    assert len(first.pairs) == 3


def test_block_claims_reports_oversized_blocks_instead_of_pairs():
    claims = [_claim(EntityType.USERNAME, "alice") for _ in range(4)]
    result = block_claims(claims, max_block_size=3)
    assert result.oversized_blocks == (("username:alice", 4),)
    assert result.pairs == ()
    assert result.blocks["username:alice"] == tuple(claim.claim_id for claim in claims)


def test_block_claims_rejects_bad_cap():
    with pytest.raises(ValueError):
        block_claims([], max_block_size=0)
