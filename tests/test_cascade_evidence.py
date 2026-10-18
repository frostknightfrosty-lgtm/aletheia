"""Tests for the claim-pair evidence decision table (P17.4)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from aletheia.cascade.claims import Claim
from aletheia.cascade.evidence import compare_claims
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


def test_identical_email_is_hard_and_other_pairs_silent():
    items = compare_claims(
        _claim(EntityType.EMAIL, "alice@example.com"),
        _claim(EntityType.EMAIL, "alice@example.com"),
    )
    assert [item.evidence_class for item in items] == [EvidenceClass.HARD]
    assert (
        compare_claims(
            _claim(EntityType.EMAIL, "alice@example.com"),
            _claim(EntityType.EMAIL, "bob@example.org"),
        )
        == []
    )
    # Public mail domains are shared infrastructure: two gmail addresses say nothing.
    assert (
        compare_claims(
            _claim(EntityType.EMAIL, "a@gmail.com"),
            _claim(EntityType.EMAIL, "b@gmail.com"),
        )
        == []
    )


def test_shared_personal_mail_domain_is_medium():
    items = compare_claims(
        _claim(EntityType.EMAIL, "alice@personal.example"),
        _claim(EntityType.EMAIL, "bob@personal.example"),
    )
    assert [item.evidence_class for item in items] == [EvidenceClass.MEDIUM]
    assert items[0].weight == pytest.approx(0.5)


def test_identical_phone_is_hard():
    assert [
        item.evidence_class
        for item in compare_claims(
            _claim(EntityType.PHONE, "+15551234567"),
            _claim(EntityType.PHONE, "+15551234567"),
        )
    ] == [EvidenceClass.HARD]
    assert (
        compare_claims(
            _claim(EntityType.PHONE, "+15551234567"),
            _claim(EntityType.PHONE, "+15557654321"),
        )
        == []
    )


def test_identical_username_is_strong():
    assert [
        item.evidence_class
        for item in compare_claims(
            _claim(EntityType.USERNAME, "frost2233"),
            _claim(EntityType.USERNAME, "frost2233"),
        )
    ] == [EvidenceClass.STRONG]
    assert (
        compare_claims(
            _claim(EntityType.USERNAME, "alice"),
            _claim(EntityType.USERNAME, "bob"),
        )
        == []
    )


def test_url_rules():
    identical = compare_claims(
        _claim(EntityType.URL, "https://alice.example/p1"),
        _claim(EntityType.URL, "https://alice.example/p1"),
    )
    assert [item.evidence_class for item in identical] == [EvidenceClass.STRONG]
    same_host = compare_claims(
        _claim(EntityType.URL, "https://alice.example/a"),
        _claim(EntityType.URL, "https://alice.example/b"),
    )
    assert [item.evidence_class for item in same_host] == [EvidenceClass.WEAK]
    assert same_host[0].weight == pytest.approx(0.4)
    # Shared platform hosts are expected by chance.
    assert (
        compare_claims(
            _claim(EntityType.URL, "https://github.com/alice"),
            _claim(EntityType.URL, "https://github.com/bob"),
        )
        == []
    )


def test_domain_rules():
    personal = compare_claims(
        _claim(EntityType.DOMAIN, "alice.example"),
        _claim(EntityType.DOMAIN, "alice.example"),
    )
    assert [item.evidence_class for item in personal] == [EvidenceClass.STRONG]
    for shared in ("gmail.com", "github.com"):
        assert (
            compare_claims(
                _claim(EntityType.DOMAIN, shared),
                _claim(EntityType.DOMAIN, shared),
            )
            == []
        )


def test_name_rules_variant_near_identical_similar_conflicting():
    variant = compare_claims(
        _claim(EntityType.NAME, "Robert Smith"),
        _claim(EntityType.NAME, "Bob Smith"),
    )
    assert [item.evidence_class for item in variant] == [EvidenceClass.MEDIUM]
    near = compare_claims(
        _claim(EntityType.PERSON, "John Smith"),
        _claim(EntityType.PERSON, "Jon Smith"),
    )
    assert [item.evidence_class for item in near] == [EvidenceClass.MEDIUM]
    assert near[0].weight == pytest.approx(0.8)
    similar = compare_claims(
        _claim(EntityType.NAME, "Smith"),
        _claim(EntityType.NAME, "Smyth"),
    )
    assert [item.evidence_class for item in similar] == [EvidenceClass.WEAK]
    conflicting = compare_claims(
        _claim(EntityType.NAME, "Robert Smith"),
        _claim(EntityType.NAME, "Zbigniew Brzezinski"),
    )
    assert [item.evidence_class for item in conflicting] == [EvidenceClass.VETO]


def test_media_rules_require_hashes_not_paths():
    sha = "ab" * 32
    strong = compare_claims(
        _claim(EntityType.IMAGE, "photos/a.png", attributes={"sha256": sha}),
        _claim(EntityType.IMAGE, "photos/b.png", attributes={"sha256": sha}),
    )
    assert [item.evidence_class for item in strong] == [EvidenceClass.STRONG]
    same_hashes = {
        "ahash": "0f0f0f0f0f0f0f0f",
        "dhash": "0f0f0f0f0f0f0f0f",
        "phash": "0f0f0f0f0f0f0f0f",
    }
    perceptual = compare_claims(
        _claim(EntityType.IMAGE, "a.png", attributes={"sha256": "0" * 64, **same_hashes}),
        _claim(EntityType.IMAGE, "b.png", attributes={"sha256": "1" * 64, **same_hashes}),
    )
    assert [item.evidence_class for item in perceptual] == [EvidenceClass.STRONG]
    assert perceptual[0].weight == pytest.approx(0.8)
    different = {
        "ahash": "ffffffffffffffff",
        "dhash": "ffffffffffffffff",
        "phash": "ffffffffffffffff",
    }
    assert (
        compare_claims(
            _claim(EntityType.IMAGE, "a.png", attributes={"sha256": "0" * 64, **same_hashes}),
            _claim(EntityType.IMAGE, "b.png", attributes={"sha256": "1" * 64, **different}),
        )
        == []
    )
    # A bare path string is not media identity.
    assert (
        compare_claims(
            _claim(EntityType.FILE, "photos/avatar.jpg"),
            _claim(EntityType.FILE, "photos/avatar.jpg"),
        )
        == []
    )


def test_vin_rules():
    vin = "1HGCM82633A004352"
    identical = compare_claims(
        _claim(EntityType.TRANSPORT_ASSET_RECORD, vin),
        _claim(EntityType.TRANSPORT_ASSET_RECORD, vin.lower()),
    )
    assert [item.evidence_class for item in identical] == [EvidenceClass.STRONG]
    conflicting = compare_claims(
        _claim(EntityType.TRANSPORT_ASSET_RECORD, vin),
        _claim(EntityType.TRANSPORT_ASSET_RECORD, "5YJ3E1EA7KF317000"),
    )
    assert [item.evidence_class for item in conflicting] == [EvidenceClass.VETO]
    assert (
        compare_claims(
            _claim(EntityType.TRANSPORT_ASSET_RECORD, "silver sedan"),
            _claim(EntityType.TRANSPORT_ASSET_RECORD, "silver sedan"),
        )
        == []
    )


def test_crypto_address_rules():
    address = "0x" + "ab" * 20
    identical = compare_claims(
        _claim(EntityType.BLOCKCHAIN_INTEL_RECORD, address),
        _claim(EntityType.BLOCKCHAIN_INTEL_RECORD, address),
    )
    assert [item.evidence_class for item in identical] == [EvidenceClass.STRONG]
    assert (
        compare_claims(
            _claim(EntityType.BLOCKCHAIN_INTEL_RECORD, address),
            _claim(EntityType.BLOCKCHAIN_INTEL_RECORD, "0x" + "cd" * 20),
        )
        == []
    )


def test_cross_type_email_domain_bridge():
    items = compare_claims(
        _claim(EntityType.EMAIL, "alice@personal.example"),
        _claim(EntityType.DOMAIN, "personal.example"),
    )
    assert [item.evidence_class for item in items] == [EvidenceClass.MEDIUM]
    assert items[0].weight == pytest.approx(0.5)
    assert (
        compare_claims(
            _claim(EntityType.EMAIL, "alice@gmail.com"),
            _claim(EntityType.DOMAIN, "gmail.com"),
        )
        == []
    )
    # No cross-type rule beyond the domain bridge.
    assert (
        compare_claims(
            _claim(EntityType.EMAIL, "frost@example.com"),
            _claim(EntityType.USERNAME, "frost"),
        )
        == []
    )


def test_origin_is_stable_and_same_claim_pair_is_rejected():
    left = _claim(EntityType.USERNAME, "frost2233", adapter="toolA", seed_index=0)
    right = _claim(EntityType.USERNAME, "frost2233", adapter="toolB", seed_index=1)
    first = compare_claims(left, right)
    second = compare_claims(left, right)
    assert first[0].origin == "toolA|seed=0|username~toolB|seed=1|username"
    assert [item.origin for item in first] == [item.origin for item in second]
    with pytest.raises(ValueError):
        compare_claims(left, left)
