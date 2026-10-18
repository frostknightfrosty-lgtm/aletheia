"""Tests for pivot extractors: bridge-map coverage and the section-7 gates."""

from __future__ import annotations

from uuid import uuid4

from aletheia.cascade.claims import Claim
from aletheia.cascade.extractors import EXTRACTOR_RULES, extract_pivots, gate_for
from aletheia.cascade.routing import BRIDGE_SEED_TYPES, TEXT_AUTODETECT_ENTITY_TYPES
from aletheia.core.models import EntityType, IdentityTier, SeedType


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


def _pairs(claim: Claim) -> list[tuple[SeedType, str]]:
    return [(pivot.seed.type, pivot.seed.value) for pivot in extract_pivots(claim)]


def test_url_claim_yields_url_and_host_canonical():
    claim = _claim(EntityType.URL, "https://Example.COM/u/alice")
    pivots = extract_pivots(claim)
    assert [(p.seed.type, p.seed.value) for p in pivots] == [
        (SeedType.URL, "https://example.com/u/alice"),
        (SeedType.DOMAIN, "example.com"),
    ]
    assert all(p.gate is IdentityTier.PROBABLE for p in pivots)
    assert all(p.claim_entity_type is EntityType.URL for p in pivots)
    assert all(p.parent_finding_id == claim.finding_id for p in pivots)


def test_domain_claim_yields_domain_and_https_url():
    assert _pairs(_claim(EntityType.DOMAIN, "Example.COM.")) == [
        (SeedType.DOMAIN, "example.com"),
        (SeedType.URL, "https://example.com"),
    ]


def test_email_claim_is_confirmed_gate():
    pivots = extract_pivots(_claim(EntityType.EMAIL, "Alice@Example.COM"))
    assert [(p.seed.type, p.seed.value) for p in pivots] == [
        (SeedType.EMAIL, "alice@example.com"),
        (SeedType.DOMAIN, "example.com"),
    ]
    assert pivots[0].gate is IdentityTier.CONFIRMED
    assert pivots[1].gate is IdentityTier.PROBABLE


def test_person_and_name_declared_gate_confirmed():
    person = extract_pivots(_claim(EntityType.PERSON, "Alice Smith"))
    assert [(p.seed.type, p.gate) for p in person] == [
        (SeedType.PERSON_NAME, IdentityTier.CONFIRMED)
    ]
    named = extract_pivots(_claim(EntityType.NAME, "Alice Smith"))
    assert [(p.seed.type, p.gate) for p in named] == [(SeedType.NAME, IdentityTier.CONFIRMED)]


def test_company_claims_are_probable():
    for entity_type in (EntityType.COMPANY, EntityType.LEGAL_ENTITY, EntityType.LEI):
        pivots = extract_pivots(_claim(entity_type, "Acme Trading LLC"))
        assert [p.seed.type for p in pivots] == [SeedType.COMPANY_NAME], entity_type
        assert pivots[0].gate is IdentityTier.PROBABLE


def test_ambiguous_record_party_yields_generic_name():
    for entity_type in (
        EntityType.SANCTION,
        EntityType.COURT_CASE,
        EntityType.FILING,
        EntityType.GOVERNMENT_RECORD,
        EntityType.COMPANY_REGISTRY_RECORD,
        EntityType.INTELLECTUAL_PROPERTY_RECORD,
    ):
        pivots = extract_pivots(_claim(entity_type, "ACME Trading"))
        assert [p.seed.type for p in pivots] == [SeedType.NAME], entity_type
        assert pivots[0].gate is IdentityTier.CONFIRMED


def test_social_account_handle_and_url():
    handle = extract_pivots(_claim(EntityType.SOCIAL_ACCOUNT, "@Frost2233"))
    assert [(p.seed.type, p.seed.value) for p in handle] == [(SeedType.USERNAME, "frost2233")]
    url = extract_pivots(_claim(EntityType.SOCIAL_ACCOUNT, "https://github.com/frost2233"))
    assert [(p.seed.type, p.seed.value) for p in url] == [
        (SeedType.URL, "https://github.com/frost2233")
    ]


def test_ocr_text_runs_autodetection():
    claim = _claim(
        EntityType.OCR_TEXT,
        "Reach alice@example.com or https://example.com/u/a, ping @alice_dev",
    )
    assert _pairs(claim) == [
        (SeedType.EMAIL, "alice@example.com"),
        (SeedType.URL, "https://example.com/u/a"),
        (SeedType.USERNAME, "alice_dev"),
    ]


def test_technical_finding_filters_to_bridge_set():
    claim = _claim(
        EntityType.TECHNICAL_FINDING,
        "contact bob@example.com or +1 (555) 123-4567, see https://git.example/x @bob_dev",
    )
    assert _pairs(claim) == [
        (SeedType.EMAIL, "bob@example.com"),
        (SeedType.URL, "https://git.example/x"),
        (SeedType.USERNAME, "bob_dev"),
    ]


def test_geo_only_from_coordinates():
    coordinate = extract_pivots(_claim(EntityType.GEO_EVIDENCE, "48.8584, 2.2945"))
    assert [(p.seed.type, p.seed.value, p.gate) for p in coordinate] == [
        (SeedType.GEOLOCATION, "48.8584,2.2945", IdentityTier.CONFIRMED)
    ]
    assert extract_pivots(_claim(EntityType.GEO_EVIDENCE, "Paris, France")) == []
    assert extract_pivots(_claim(EntityType.PLACE, "Paris")) == []
    place_coordinate = extract_pivots(_claim(EntityType.PLACE, "48.8584 2.2945"))
    assert [(p.seed.type, p.seed.value) for p in place_coordinate] == [
        (SeedType.GEOLOCATION, "48.8584,2.2945")
    ]


def test_transport_vin_vs_plain_value():
    vin = extract_pivots(_claim(EntityType.TRANSPORT_ASSET_RECORD, "1hgcm82633a004352"))
    assert [(p.seed.type, p.seed.value, p.gate) for p in vin] == [
        (SeedType.VIN, "1HGCM82633A004352", IdentityTier.PROBABLE)
    ]
    assert extract_pivots(_claim(EntityType.TRANSPORT_ASSET_RECORD, "Cessna 172")) == []


def test_blockchain_rule_address_vs_url():
    address = extract_pivots(
        _claim(EntityType.BLOCKCHAIN_INTEL_RECORD, "1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
    )
    assert [(p.seed.type, p.seed.value) for p in address] == [
        (SeedType.CRYPTO_ADDRESS, "1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
    ]
    url = extract_pivots(_claim(EntityType.BLOCKCHAIN_INTEL_RECORD, "https://example.com/donate"))
    assert [(p.seed.type, p.seed.value) for p in url] == [
        (SeedType.URL, "https://example.com/donate")
    ]


def test_email_auth_rule_finds_domain_in_record_text():
    pivots = extract_pivots(
        _claim(EntityType.EMAIL_AUTH_RECORD, "v=spf1 include:spf.example.com ~all")
    )
    assert [(p.seed.type, p.seed.value) for p in pivots] == [
        (SeedType.DOMAIN, "spf.example.com")
    ]


def test_seed_index_carries_into_pivots():
    pivots = extract_pivots(_claim(EntityType.USERNAME, "alice", seed_index=3))
    assert pivots[0].seed_index == 3


def test_every_bridged_entity_type_has_a_rule_and_terminals_do_not():
    expected = set(BRIDGE_SEED_TYPES) | set(TEXT_AUTODETECT_ENTITY_TYPES)
    assert set(EXTRACTOR_RULES) == expected


def test_rule_fixture_walk_stays_inside_bridge_maps():
    fixtures = {
        EntityType.URL: "https://example.com/u/a",
        EntityType.DOMAIN: "example.com",
        EntityType.HOST: "example.com",
        EntityType.EMAIL: "alice@example.com",
        EntityType.USERNAME: "alice",
        EntityType.IP: "8.8.8.8",
        EntityType.PHONE: "+15551234567",
        EntityType.FILE: "/tmp/evidence.jpg",
        EntityType.IMAGE: "/tmp/evidence.jpg",
        EntityType.PERSON: "Alice Smith",
        EntityType.NAME: "Alice Smith",
        EntityType.COMPANY: "Acme LLC",
        EntityType.LEGAL_ENTITY: "Acme LLC",
        EntityType.LEI: "5493001KJTIIGC8Y1R12",
        EntityType.FILING: "ACME Trading",
        EntityType.COURT_CASE: "ACME Trading",
        EntityType.SANCTION: "ACME Trading",
        EntityType.GOVERNMENT_RECORD: "ACME Trading",
        EntityType.COMPANY_REGISTRY_RECORD: "ACME Trading",
        EntityType.INTELLECTUAL_PROPERTY_RECORD: "ACME Trading",
        EntityType.ACADEMIC_RECORD: "Alice Smith",
        EntityType.SOCIAL_ACCOUNT: "frost2233",
        EntityType.BREACH: "alice@example.com",
        EntityType.TLS_OBSERVATION: "example.com",
        EntityType.BLOCKCHAIN_INTEL_RECORD: "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
        EntityType.EMAIL_AUTH_RECORD: "example.com",
        EntityType.TECHNICAL_FINDING: "contact bob@example.com",
        EntityType.WEB_SEARCH_RESULT: "https://example.com/a",
        EntityType.GEOLOCATION: "48.8584, 2.2945",
        EntityType.GEO_EVIDENCE: "48.8584, 2.2945",
        EntityType.PLACE: "48.8584, 2.2945",
        EntityType.TRANSPORT_ASSET_RECORD: "1hgcm82633a004352",
        EntityType.OCR_TEXT: "ping @alice_dev",
    }
    assert set(fixtures) == set(EXTRACTOR_RULES)
    for entity_type, value in fixtures.items():
        pivots = extract_pivots(_claim(entity_type, value))
        assert pivots, entity_type
        allowed = (
            frozenset(SeedType)
            if entity_type in TEXT_AUTODETECT_ENTITY_TYPES
            else BRIDGE_SEED_TYPES[entity_type]
        )
        for pivot in pivots:
            assert pivot.seed.type in allowed, (entity_type, pivot.seed.type)


def test_gate_table():
    confirmed = {
        SeedType.EMAIL,
        SeedType.PHONE,
        SeedType.PERSON_NAME,
        SeedType.NAME,
        SeedType.GEOLOCATION,
    }
    for seed_type in SeedType:
        expected = IdentityTier.CONFIRMED if seed_type in confirmed else IdentityTier.PROBABLE
        assert gate_for(seed_type) is expected
