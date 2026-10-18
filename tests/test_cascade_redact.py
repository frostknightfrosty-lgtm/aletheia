"""Tests for deterministic artifact redaction (P17.8)."""

from __future__ import annotations

from aletheia.cascade.dossier import DossierCluster, DossierField, EvidenceRef, build_dossier
from aletheia.cascade.redact import redact_dossier, redact_token, redact_trail
from aletheia.cascade.trail import TrailHop, build_trail
from aletheia.core.models import EntityType, IdentityTier, Seed, SeedType


def test_redact_token_is_deterministic():
    assert redact_token("a@example.com") == redact_token("a@example.com")
    assert redact_token("a@example.com") != redact_token("b@example.com")
    assert redact_token("a@example.com").startswith("redacted:")


def test_redact_trail_touches_only_person_types():
    trail = build_trail(
        [
            TrailHop(hop_id="a", seed_type=SeedType.EMAIL, seed_value="alice@example.com", depth=1, outcome="expanded"),
            TrailHop(hop_id="b", parent_hop_id="a", seed_type=SeedType.USERNAME, seed_value="alice", depth=2, outcome="empty"),
        ]
    )
    redacted = redact_trail(trail)
    assert redacted["hops"][0]["seed_value"] == redact_token("alice@example.com")
    assert redacted["hops"][1]["seed_value"] == "alice"
    # the original mapping is untouched
    assert trail["hops"][0]["seed_value"] == "alice@example.com"
    # structural fields survive
    assert redacted["hops"][1]["parent_hop_id"] == "a"
    assert redacted["hops"][0]["depth"] == 1


def test_redact_dossier_tokens_subject_and_fields():
    dossier = build_dossier(
        subject_seeds=[
            Seed(type=SeedType.USERNAME, value="frost2233"),
            Seed(type=SeedType.EMAIL, value="f@example.com"),
        ],
        clusters=[
            DossierCluster(
                "c",
                IdentityTier.CONFIRMED,
                (
                    DossierField(EntityType.EMAIL, "alice@example.com", (EvidenceRef("profile", "github"),)),
                    DossierField(EntityType.USERNAME, "alice"),
                ),
            )
        ],
    )
    redacted = redact_dossier(dossier)
    fields = redacted["clusters"][0]["fields"]
    assert fields[0]["value"] == redact_token("alice@example.com")
    assert fields[0]["evidence"] == [{"kind": "profile", "source": "github", "note": ""}]
    assert fields[1]["value"] == "alice"
    assert redacted["subject"][0]["value"] == "frost2233"
    assert redacted["subject"][1]["value"] == redact_token("f@example.com")
    # the original dossier is untouched
    assert dossier["clusters"][0]["fields"][0]["value"] == "alice@example.com"
    assert dossier["subject"][1]["value"] == "f@example.com"
