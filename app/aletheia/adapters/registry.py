from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aletheia.adapters.exiftool import ExifToolAdapter
from aletheia.adapters.identity import (
    H8mailAdapter, HIBPAdapter, HoleheAdapter, LibPhoneNumberAdapter, MaigretAdapter,
    PhoneInfogaAdapter, VenomAdapter, XposedOrNotAdapter, ZehefAdapter,
)
from aletheia.adapters.sherlock import SherlockAdapter
from aletheia.adapters.theharvester import TheHarvesterAdapter
from aletheia.adapters.infra import (
    AmassAdapter, AssetfinderAdapter, DnsreconAdapter, DnsxAdapter,
    FierceAdapter, MassdnsAdapter, ShodanAdapter, SubfinderAdapter, CrtshAdapter,
)
from aletheia.core.adapters import Adapter
from aletheia.core.project_manifest import enforce_adapter_tier_policy, load_project_manifest
from aletheia.adapters.corporate_records import (SECEdgarAdapter, GLEIFAdapter, OpenCorporatesAdapter, OpenSanctionsAdapter, CourtListenerAdapter)
from aletheia.adapters.social_geo_image import (
    DeepFaceAdapter, InsightFaceAdapter, InstaloaderAdapter,
    OverpassAdapter, PicImageSearchAdapter, RedditAPIAdapter, SunCalcAdapter,
    TiktokHashtagAdapter, YouTubeAPIAdapter,
)
from aletheia.adapters.tracelines import TracelinesAdapter
from aletheia.adapters.phase5c import GravatarAdapter, RdapAdapter
from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter
from aletheia.adapters.corporate_registry import CorporateRegistryAdapter
from aletheia.adapters.sanctions_enforcement_watchlists import SanctionsEnforcementWatchlistsAdapter
from aletheia.adapters.academic_search import AcademicSearchAdapter
from aletheia.adapters.ssl_tls import SslTlsAdapter
from aletheia.adapters.ip_intelligence import IPIntelligenceAdapter
from aletheia.adapters.crypto_blockchain import CryptoBlockchainAdapter
from aletheia.adapters.patents_trademarks import PatentsTrademarksAdapter
from aletheia.adapters.email_auth import EmailAuthAdapter
from aletheia.adapters.code_search import CodeSearchAdapter
from aletheia.adapters.search_engines import SearchEnginesAdapter
from aletheia.adapters.geolocation_image import GeolocationImageAdapter
from aletheia.adapters.transport_asset_registry import TransportAssetRegistryAdapter
from aletheia.adapters.social_profile import SocialProfileAdapter
from aletheia.adapters.social_username import SocialUsernameAdapter
from aletheia.adapters.leak_checkers import LeakCheckersAdapter


def phase1_adapters() -> dict[str, Adapter]:
    adapters = [SherlockAdapter(), TheHarvesterAdapter(), ExifToolAdapter()]
    return {a.descriptor.name: a for a in adapters}


def phase3_adapters() -> dict[str, Adapter]:
    adapters = [
        *phase1_adapters().values(),
        AmassAdapter(), SubfinderAdapter(), AssetfinderAdapter(), DnsxAdapter(), MassdnsAdapter(),
        DnsreconAdapter(), FierceAdapter(), ShodanAdapter(), CrtshAdapter(),
    ]
    return {a.descriptor.name: a for a in adapters}


def phase4_adapters() -> dict[str, Adapter]:
    adapters = [
        *phase3_adapters().values(),
        MaigretAdapter(), HoleheAdapter(), H8mailAdapter(), HIBPAdapter(), XposedOrNotAdapter(),
        PhoneInfogaAdapter(), LibPhoneNumberAdapter(),
    ]
    return {a.descriptor.name: a for a in adapters}


def phase5_adapters() -> dict[str, Adapter]:
    adapters = [
        *phase4_adapters().values(),
        InstaloaderAdapter(), RedditAPIAdapter(), YouTubeAPIAdapter(), OverpassAdapter(),
        SunCalcAdapter(), DeepFaceAdapter(), InsightFaceAdapter(),
    ]
    return {a.descriptor.name: a for a in adapters}


def phase6_adapters() -> dict[str, Adapter]:
    adapters = [
        *phase5_adapters().values(),
        SECEdgarAdapter(), GLEIFAdapter(), OpenCorporatesAdapter(), OpenSanctionsAdapter(), CourtListenerAdapter(),
    ]
    return {a.descriptor.name: a for a in adapters}


MANIFEST_PATH = Path(__file__).resolve().parents[3] / "PROJECT_MANIFEST.json"


@lru_cache(maxsize=1)
def _manifest_entries() -> dict:
    """The repository manifest, validated once per process."""
    return load_project_manifest(MANIFEST_PATH)


def phase7_adapters() -> dict[str, Adapter]:
    # Phase 7 adds control-plane capabilities; external collectors remain the Phase 6 registry.
    adapters = phase6_adapters()
    adapters[GravatarAdapter.descriptor.name] = GravatarAdapter()
    adapters[RdapAdapter.descriptor.name] = RdapAdapter()
    adapters[IPIntelligenceAdapter.descriptor.name] = IPIntelligenceAdapter()
    adapters[GovernmentRecordsUSAdapter.descriptor.name] = GovernmentRecordsUSAdapter()
    adapters[CorporateRegistryAdapter.descriptor.name] = CorporateRegistryAdapter()
    adapters[SanctionsEnforcementWatchlistsAdapter.descriptor.name] = SanctionsEnforcementWatchlistsAdapter()
    adapters[AcademicSearchAdapter.descriptor.name] = AcademicSearchAdapter()
    adapters[SslTlsAdapter.descriptor.name] = SslTlsAdapter()
    adapters[CryptoBlockchainAdapter.descriptor.name] = CryptoBlockchainAdapter()
    adapters[PatentsTrademarksAdapter.descriptor.name] = PatentsTrademarksAdapter()
    adapters[EmailAuthAdapter.descriptor.name] = EmailAuthAdapter()
    adapters[CodeSearchAdapter.descriptor.name] = CodeSearchAdapter()
    adapters[SearchEnginesAdapter.descriptor.name] = SearchEnginesAdapter()
    adapters[GeolocationImageAdapter.descriptor.name] = GeolocationImageAdapter()
    adapters[TransportAssetRegistryAdapter.descriptor.name] = TransportAssetRegistryAdapter()
    adapters[SocialProfileAdapter.descriptor.name] = SocialProfileAdapter()
    adapters[SocialUsernameAdapter.descriptor.name] = SocialUsernameAdapter()
    adapters[LeakCheckersAdapter.descriptor.name] = LeakCheckersAdapter()
    adapters[ZehefAdapter.descriptor.name] = ZehefAdapter()
    adapters[TiktokHashtagAdapter.descriptor.name] = TiktokHashtagAdapter()
    adapters[VenomAdapter.descriptor.name] = VenomAdapter()
    adapters[PicImageSearchAdapter.descriptor.name] = PicImageSearchAdapter()
    adapters[TracelinesAdapter.descriptor.name] = TracelinesAdapter()
    # Construction-time Tier 5 rejection: every adapter must have a manifest
    # entry, and an entry declaring legal_tier=5 refuses construction.
    enforce_adapter_tier_policy(adapters.keys(), manifest=_manifest_entries())
    return adapters
