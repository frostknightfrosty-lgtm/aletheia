from __future__ import annotations

from aletheia.adapters.exiftool import ExifToolAdapter
from aletheia.adapters.identity import (
    H8mailAdapter, HIBPAdapter, HoleheAdapter, LibPhoneNumberAdapter, MaigretAdapter,
    PhoneInfogaAdapter, XposedOrNotAdapter,
)
from aletheia.adapters.sherlock import SherlockAdapter
from aletheia.adapters.theharvester import TheHarvesterAdapter
from aletheia.adapters.infra import (
    AmassAdapter, AssetfinderAdapter, DnsreconAdapter, DnsxAdapter,
    FierceAdapter, MassdnsAdapter, ShodanAdapter, SubfinderAdapter, CrtshAdapter,
)
from aletheia.core.adapters import Adapter
from aletheia.adapters.corporate_records import (SECEdgarAdapter, GLEIFAdapter, OpenCorporatesAdapter, OpenSanctionsAdapter, CourtListenerAdapter)
from aletheia.adapters.social_geo_image import (
    DeepFaceAdapter, InsightFaceAdapter, InstaloaderAdapter,
    OverpassAdapter, RedditAPIAdapter, SunCalcAdapter, YouTubeAPIAdapter,
)
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
    return adapters
