"""Tests for the tiered dossier artifact (P17.8)."""

from __future__ import annotations

import pytest

from aletheia.cascade.dossier import DossierCluster, DossierField, EvidenceRef, build_dossier
from aletheia.core.models import EntityType, IdentityTier, Seed, SeedType


def test_build_dossier_orders_and_flags_unsupported():
    dossier = build_dossier(
        subject_seeds=[Seed(type=SeedType.USERNAME, value="frost2233")],
        clusters=[
            DossierCluster("z-new", None, (DossierField(EntityType.USERNAME, "frost2233"),)),
            DossierCluster(
                "a-confirmed",
                IdentityTier.CONFIRMED,
                (
                    DossierField(EntityType.EMAIL, "a@example.com", (EvidenceRef("oauth-profile", "github"),)),
                    DossierField(EntityType.DOMAIN, "example.com"),
                ),
            ),
        ],
        run_id="r1",
    )
    assert [cluster["cluster_id"] for cluster in dossier["clusters"]] == ["a-confirmed", "z-new"]
    fields = dossier["clusters"][0]["fields"]
    assert [field["entity_type"] for field in fields] == ["domain", "email"]
    assert fields[0]["supported"] is False
    assert fields[1]["supported"] is True
    assert fields[1]["evidence"][0] == {"kind": "oauth-profile", "source": "github", "note": ""}
    assert dossier["clusters"][1]["tier"] is None
    assert dossier["subject"][0]["value"] == "frost2233"


def test_build_dossier_validation():
    with pytest.raises(ValueError):
        build_dossier(subject_seeds=[], clusters=[])
    seed = [Seed(type=SeedType.USERNAME, value="x")]
    with pytest.raises(ValueError):
        build_dossier(
            subject_seeds=seed,
            clusters=[DossierCluster("a", None), DossierCluster("a", None)],
        )
    with pytest.raises(ValueError):
        build_dossier(subject_seeds=seed, clusters=[DossierCluster("", None)])
    with pytest.raises(ValueError):
        build_dossier(
            subject_seeds=seed,
            clusters=[DossierCluster("a", "confirmed")],  # type: ignore[arg-type]
        )


def test_build_dossier_is_deterministic():
    kwargs = dict(
        subject_seeds=[Seed(type=SeedType.USERNAME, value="x")],
        clusters=[
            DossierCluster(
                "b",
                IdentityTier.POSSIBLE,
                (
                    DossierField(EntityType.URL, "https://b.example"),
                    DossierField(EntityType.URL, "https://a.example"),
                ),
            )
        ],
    )
    first = build_dossier(**kwargs)
    second = build_dossier(**kwargs)
    assert first == second
    assert [f["value"] for f in first["clusters"][0]["fields"]] == [
        "https://a.example",
        "https://b.example",
    ]
