"""Skip and error markers are not domain records.

Readiness audit 2026-10-25: batch adapters recorded ``<source>:skipped`` and
``<source>:error`` markers with their own domain entity type (a skipped sanctions
source looked like a ``sanction`` record, a skipped TLS source like a TLS
observation, and so on). Markers are ``EntityType.UNKNOWN``; real records keep
their domain type. Descriptors are intentionally unchanged: the cascade router
builds its graph from ``descriptor.output_types`` and existing tests pin them.
"""
import importlib

import pytest

from aletheia.core.models import EntityType

CASES = [
    ("academic_search", "AcademicSearchFinding", EntityType.ACADEMIC_RECORD),
    ("code_search", "TechnicalFinding", EntityType.TECHNICAL_FINDING),
    ("corporate_registry", "CorporateRegistryFinding", EntityType.COMPANY_REGISTRY_RECORD),
    ("crypto_blockchain", "CryptoBlockchainFinding", EntityType.BLOCKCHAIN_INTEL_RECORD),
    ("email_auth", "EmailAuthFinding", EntityType.EMAIL_AUTH_RECORD),
    ("geolocation_image", "GeoEvidenceFinding", EntityType.GEO_EVIDENCE),
    ("government_records_us", "GovernmentRecordsUSFinding", EntityType.GOVERNMENT_RECORD),
    ("patents_trademarks", "PatentsTrademarksFinding", EntityType.INTELLECTUAL_PROPERTY_RECORD),
    ("sanctions_enforcement_watchlists", "SanctionsEnforcementWatchlistsFinding", EntityType.SANCTION),
    ("search_engines", "WebSearchResult", EntityType.WEB_SEARCH_RESULT),
    ("ssl_tls", "SslTlsFinding", EntityType.TLS_OBSERVATION),
    ("transport_asset_registry", "TransportAssetFinding", EntityType.TRANSPORT_ASSET_RECORD),
]
IDS = [module for module, _, _ in CASES]


def _cls(module, name):
    return getattr(importlib.import_module(f"aletheia.adapters.{module}"), name)


@pytest.mark.parametrize("module,name,domain_type", CASES, ids=IDS)
@pytest.mark.parametrize("suffix", [":skipped", ":error"])
def test_marker_records_are_unknown(module, name, domain_type, suffix):
    finding = _cls(module, name)(subject=f"some-source{suffix}", source="some-source")
    assert finding.entity_type == EntityType.UNKNOWN
    assert finding.value == f"some-source{suffix}"


@pytest.mark.parametrize("module,name,domain_type", CASES, ids=IDS)
def test_real_records_keep_their_domain_type(module, name, domain_type):
    finding = _cls(module, name)(subject="a-real-record-id", source="some-source")
    assert finding.entity_type == domain_type
