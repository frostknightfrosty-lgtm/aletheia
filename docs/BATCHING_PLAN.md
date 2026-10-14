# Aletheia Batching Plan

Derived from `docs/VERIFICATION_COMPLETE.md`. The 111 accepted candidates are organized into 21 composite adapters and 9 one-off adapters.

Purpose: implement each composite adapter as one Docker container that queries related sub-sources, normalizes their output into a common schema, and registers once in `PROJECT_MANIFEST.json`. This collapses 111 candidate integrations into about 20 composite builds plus the specialized one-offs while retaining source coverage.

## Planning status and assumptions

- The source set and ACCEPT decisions are transcribed from the recovered Gemini verification tables; this plan does not independently re-verify upstream APIs, terms, availability, or quotas.
- `legal_tier` for a composite is the highest tier among its sub-sources. `enabled_by_default` is planned as `true` for each composite and each sub-source, with any required free key enforced as a runtime availability/configuration condition rather than by fabricating credentials.
- Rate limits are per-source registry fields. The table below preserves rate/quota details when the recovered verification notes state them. If no explicit quota was recorded, the value is marked unknown and must be confirmed from the official source before implementation or live requests. Do not treat this transcript as current rate-limit verification.
- Each composite is planned to have one manifest entry (`legal_tier`, `enabled_by_default: true`, `batch_grouping`), one Docker image, one fixture containing representative output from every sub-source, and one parser that dispatches by source identifier. Tests and capture cases must cover every source path.
- The social profile composite must preserve the project’s read-only output constraint for CrossLinked: `name`, `username`, `email`, `company`, and `source_url` only.

## Implementation status (2026-10-15) — plan checked against the built adapters

This plan is a transcript of recovered verification notes. Its own planning-status section warns that
it "does not independently re-verify upstream APIs, terms, availability, or quotas". Two rows have now
been disproved on re-verification, and four composites have absorbed rows or sub-sources assigned
elsewhere. Before implementing any remaining composite, diff its sub-source list against
`PROJECT_MANIFEST.json` and build only what is not already live.

| Row | Status |
| --- | --- |
| `ip_intelligence_geo` + `_reputation` + `_threat_exposure` | Merged into one `ip_intelligence` adapter (15 sub-sources). All three rows are complete. |
| `government_records_us` | Complete as an 11-sub-source adapter. It implements its own 4 sub-sources **plus 7 the plan assigned to other rows**: `finra-brokercheck`, `fed-enforcement`, `occ-enforcement` (this plan's `sanctions_enforcement_watchlists`) and `fdic-bankfind`, `lda`, `usaspending`, `sam-gov` (this plan's `corporate_financial_public_records`). |
| `corporate_registry` | Complete (8 sub-source entries). KVK is split into a paid name search and a free number-keyed Open Dataset, and the official French DINUM `recherche-entreprises` API stands in where INPI publishes no free search API. |
| `sanctions_enforcement_watchlists` | Complete for the 3 sub-sources its row did not already have live: `uk-sanctions-list`, `swiss-seco`, `eu-consolidated-sanctions`. The row's other 3 sub-sources are in `government_records_us`; they are not duplicated. |
| `corporate_financial_public_records` | **Not built — source unavailable.** 4 of its 5 sub-sources are already in `government_records_us`. The 5th, FollowTheMoney, publishes no request-parameter contract for name queries, and its parent OpenSecrets discontinued public API access on 2025-04-15 and now offers only a commercial route. See `docs/NOT_INTEGRATED.md`. |

## Composite adapters

| Batch adapter | Sub-sources (from verification) | Input types | Output schema | Legal tier | Est. sessions |
| --- | --- | --- | --- | ---: | ---: |
| `ip_intelligence_geo` | IPinfo API; IP-API; ipapi.co; IPGeolocation.io; ipinfo.app ASN Lookup API | ip, asn, domain, user-agent | `IpIntelRecord` | Tier 3 | 2 |
| `ip_intelligence_reputation` | AbuseIPDB API v2; GreyNoise Community API; VirusTotal API v3; Netlas API | ip, cidr, domain, url, hash, asn | `IpReputationRecord` | Tier 3 | 2 |
| `ip_intelligence_threat_exposure` | URLhaus Community API; ThreatFox Community API; MalwareBazaar Community API; PhishTank API; FullHunt API; HackerTarget API | url, domain, ip, hash, md5, sha1, sha256, hostname, cidr, asn | `ThreatIndicator` | Tier 3 | 2 |
| `corporate_registry` | Companies House API; Data INPI RNE; KVK Business Register API; ASIC Registry APIs; NZBN API; CIPC / BizPortal | company name, company number, officer name, siren/siret, kvk number, acn/abn, nzbn, enterprise number | `CompanyRegistryRecord` | Tier 3 | 2 |
| `sanctions_enforcement_watchlists` | UK Sanctions List; Swiss SECO Sanctions List; EU Consolidated Sanctions; FINRA BrokerCheck; Federal Reserve Enforcement Actions; OCC Enforcement Actions Search | person name, entity name, company name, organisation name, crd number, bank name | `ComplianceRecord` | Tier 2 | 2 |
| `corporate_financial_public_records` | FDIC BankFind Suite API; FollowTheMoney API; Lobbying Disclosure Act API; USAspending API; SAM.gov APIs | bank name, institution id, donor name, candidate, lobbyist name, organisation, company name, recipient id, uei, cage code | `FinancialDisclosureRecord` | Tier 3 | 2 |
| `government_records_us` | FOIA.gov API; NHTSA vPIC; Federal BOP Inmate Locator; NYC Open Data API | agency, office, vin, name, register number, person name, date, location | `GovernmentRecord` | Tier 3 | 2 |
| `geolocation_image` | PicImageSearch; Mapillary API v4; tracelines; Nominatim/Photon (`geoaddress`); Copernicus Data Space | image file, url, coordinates, bbox, place, date | `GeoEvidence` | Tier 3 | 2 |
| `transport_movement` | OpenSky Network API; BarentsWatch AIS API; Network Rail Open Data; National Rail Data; Deutsche Bahn Timetables API | icao24, time, bbox, mmsi, coordinates, train/service identifier, station, service, train, date | `TransportObservation` | Tier 3 | 2 |
| `transport_asset_registry` | FAA Aircraft Registration; OpenRailwayMap API; ERATV; Planespotters API | tail number, station/facility, uic, vehicle type, aircraft registration, hex | `TransportAssetRecord` | Tier 1 | 2 |
| `leak_checkers` | BreachDirectory; Leak-Lookup; LeakIX; GrayhatWarfare; Bron Vault | email, username, domain, ip, phone, password, keyword, file extension, local log files | `ExposureIndexRecord` | Tier 4 | 2 |
| `patents_trademarks` | PatentsView; USPTO Open Data Portal; USPTO Patent Assignment Search; USPTO TSDR; EUIPO eSearch plus | patent number, inventor, assignee, patent, trademark, assignor, trademark serial/reg number, mark/name, owner | `IntellectualPropertyRecord` | Tier 3 | 2 |
| `academic_search` | OpenAlex API; Crossref REST API; Semantic Scholar; arXiv API; CORE API | author, institution, DOI, title, paper title, category, id | `AcademicRecord` | Tier 3 | 2 |
| `research_discovery` | EPO OPS; Google Patents Public Datasets; Unpaywall API; OpenAIRE Graph API | publication/app number, applicant, patent number, inventor, assignee, DOI, email, title, author | `ResearchArtifact` | Tier 3 | 2 |
| `social_username` | OWASP SocialOSINTLM; Masto; Octosuite; scrawler | username, instance, org, repo, URL | `SocialAccountFinding` | Tier 3 | 2 |
| `social_profile` | CrossLinked; Slinky; tiktok-hashtag-analysis; Zehef | company name, URL, hashtag, email | `SocialProfileFinding` | Tier 2 | 2 |
| `darkweb_search` | OnionSearch; TorBot; Piano (darknet-crawler); Intelligence X | keyword, URL, email, domain, IP, hash | `DarkwebSearchFinding` | Tier 4 | 2 |
| `crypto_blockchain` | mempool.space API; Blockstream Esplora; Blockchair API; Etherscan API V2; BlockCypher; Chainabuse | BTC address, txid, address, EVM address, URL | `BlockchainIntelRecord` | Tier 3 | 2 |
| `technical_surface_search` | GitLab Search API; Debian Code Search API; PublicWWW API; checkdmarc; scan.mx API | keyword, code snippet, package, source-code snippet, domain, DNS records | `TechnicalFinding (typed finding_kind)` | Tier 3 | 2 |
| `search_engines` | SearXNG; Marginalia Search API; Google Custom Search JSON API; Common Crawl Index API | keyword, domain, URL | `WebSearchResult` | Tier 3 | 2 |
| `ssl_tls` | Qualys SSL Labs API; testssl.sh; CipherScan; CertGraph; sslscan; tlsx | domain, hostname, IP, port, CIDR, ASN | `TlsObservation` | Tier 1 | 2 |

Composite estimates total **42 sessions** (2 sessions per composite). These are planning estimates, not implementation commitments or verified durations.

## Source registry plan

Every listed sub-source gets its own registry record inside its composite adapter. The source-specific `rate_limit` value below is copied from the recovered candidate notes when an explicit quota appears there; otherwise it is explicitly unknown and must be checked against official documentation before the adapter is implemented. `enabled_by_default` is planned `true` for every accepted source, consistent with the project direction; required keys remain a runtime prerequisite.

| batch_grouping | sub-source | input types | legal tier | auth/key noted in verification | rate_limit evidence / implementation field | enabled_by_default |
| --- | --- | --- | ---: | --- | --- | --- |
| `ip_intelligence_geo` | IPinfo API | ip, asn | Tier 3 | Free API Token | 50,000 req/mo free on signup; returns IP geo, ASN, hostname, company org. | true |
| `ip_intelligence_geo` | IP-API | ip, domain | Tier 1 | None (Unauthenticated) | 45 req/min free HTTP unauthenticated; IP geolocation & ASN resolution. | true |
| `ip_intelligence_geo` | ipapi.co | ip | Tier 1 | None / Free Key | 1,000 req/day (30k/mo) free unauthenticated tier for IP location/network data. | true |
| `ip_intelligence_geo` | IPGeolocation.io | ip, domain, user-agent | Tier 3 | Free API Key | Free tier provides 1,000 req/day (30,000/mo) for IP geolocation & threat intel. | true |
| `ip_intelligence_geo` | ipinfo.app ASN Lookup API | asn, ip | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_reputation` | AbuseIPDB API v2 | ip, cidr | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_reputation` | GreyNoise Community API | ip | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_reputation` | VirusTotal API v3 | ip, domain, url, hash | Tier 3 | Free API Key | 4 req/min, 500 req/day, 15,000 req/mo public API quota for multi-engine detections. | true |
| `ip_intelligence_reputation` | Netlas API | ip, cidr, domain, asn | Tier 3 | Free API Key | Community plan grants free API key with 2,500 coins/queries monthly. | true |
| `ip_intelligence_threat_exposure` | URLhaus Community API | url, domain, ip | Tier 3 | Free `Auth-Key` (`auth.abuse.ch`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_threat_exposure` | ThreatFox Community API | ip, domain, url, hash | Tier 3 | Free `Auth-Key` (`auth.abuse.ch`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_threat_exposure` | MalwareBazaar Community API | hash (md5, sha1, sha256) | Tier 3 | Free `Auth-Key` (`auth.abuse.ch`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_threat_exposure` | PhishTank API | url | Tier 1 / 3 | Optional Free `app_key` | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_threat_exposure` | FullHunt API | domain, hostname, ip | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ip_intelligence_threat_exposure` | HackerTarget API | ip, domain, cidr, asn | Tier 1 | None (Unauthenticated) | 50 queries/day free unauthenticated for ASN lookup, reverse IP, and ping tools. | true |
| `corporate_registry` | Companies House API | company name, company number, officer name | Tier 3 | Free API Key | Official UK corporate registry; free API key, 600 req/5min rate limit. | true |
| `corporate_registry` | Data INPI RNE | company name, siren/siret | Tier 1 / 3 | Free Portal Key / Open API | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_registry` | KVK Business Register API | company name, kvk number | Tier 3 | Free Developer Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_registry` | ASIC Registry APIs | company name, acn/abn | Tier 3 | Free GUID Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_registry` | NZBN API | company name, nzbn | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_registry` | CIPC / BizPortal | company name, enterprise number | Tier 3 | OAuth 2.0 Credentials | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | UK Sanctions List | person name, entity name | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | Swiss SECO Sanctions List | person name, company name | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | EU Consolidated Sanctions | person name, organisation name | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | FINRA BrokerCheck | person name, crd number | Tier 2 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | Federal Reserve Enforcement Actions | person name, bank name | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `sanctions_enforcement_watchlists` | OCC Enforcement Actions Search | bank name, person name | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_financial_public_records` | FDIC BankFind Suite API | bank name, institution id | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_financial_public_records` | FollowTheMoney API | donor name, candidate | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_financial_public_records` | Lobbying Disclosure Act API | lobbyist name, organisation | Tier 1 / 3 | Anonymous / Free Token | Migrated to `lda.gov/api/v1/`; provides 15 req/min anonymous access and free token registration for 120 req/min. | true |
| `corporate_financial_public_records` | USAspending API | company name, recipient id | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `corporate_financial_public_records` | SAM.gov APIs | company name, uei, cage code | Tier 3 | Free API Key (`api.data.gov`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `government_records_us` | FOIA.gov API | agency, office | Tier 3 | Free API Key (`api.data.gov`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `government_records_us` | NHTSA vPIC | vin | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `government_records_us` | Federal BOP Inmate Locator | name, register number | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `government_records_us` | NYC Open Data API | person name, date, location | Tier 1 | None / Free App Token | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `geolocation_image` | PicImageSearch | image file, url | Tier 2 | Dependent on engine | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `geolocation_image` | Mapillary API v4 | coordinates, bbox | Tier 3 | Free Client Token | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `geolocation_image` | tracelines | bbox | Tier 1 | None | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `geolocation_image` | Nominatim/Photon (`geoaddress`) | place, coordinates | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `geolocation_image` | Copernicus Data Space | bbox, date | Tier 1 / 3 | Free Registered Account | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_movement` | OpenSky Network API | icao24, time, bbox | Tier 1 / 3 | None / Free Key | Public community flight tracking; free anonymous access (~400 req/day) and free registered key (~4,000 req/day). | true |
| `transport_movement` | BarentsWatch AIS API | mmsi, time, coordinates | Tier 3 | Free OAuth 2.0 Credentials | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_movement` | Network Rail Open Data | train/service identifier | Tier 3 | Free Self-service Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_movement` | National Rail Data | station, service | Tier 3 | Free Developer Token | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_movement` | Deutsche Bahn Timetables API | station, train, date | Tier 3 | Free Client-ID & Secret | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_asset_registry` | FAA Aircraft Registration | tail number | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_asset_registry` | OpenRailwayMap API | station/facility, uic | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_asset_registry` | ERATV | vehicle type | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `transport_asset_registry` | Planespotters API | aircraft registration, hex | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `leak_checkers` | BreachDirectory | email, username, domain | Tier 4 | Free RapidAPI Key | Basic free tier provides 10 requests/month with free RapidAPI subscription; returns breach indicator and SHA-1 password hashes. | true |
| `leak_checkers` | Leak-Lookup | email, username, ip, phone, password | Tier 4 | Free Public API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `leak_checkers` | LeakIX | domain, ip, keyword | Tier 4 | Free Registered Key | Public index of exposed services and database leaks; free registered API key allows 3,000 requests/month (`api-key: <key>`). | true |
| `leak_checkers` | GrayhatWarfare | keyword, file extension | Tier 2 | Free Access Token | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `leak_checkers` | Bron Vault | local log files | Tier 4 | None (Local execution) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `patents_trademarks` | PatentsView | patent number, inventor, assignee | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `patents_trademarks` | USPTO Open Data Portal | patent, trademark | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `patents_trademarks` | USPTO Patent Assignment Search | patent number, assignor, assignee | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `patents_trademarks` | USPTO TSDR | trademark serial/reg number | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `patents_trademarks` | EUIPO eSearch plus | mark/name, owner | Tier 3 | Free Developer Key / OAuth | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `academic_search` | OpenAlex API | author, institution, DOI | Tier 1 | None / Polite Email | Open bibliographic graph indexing 250M+ works; unauthenticated access grants 100,000 calls/day; Polite pool via email header. | true |
| `academic_search` | Crossref REST API | title, author, DOI | Tier 1 | None / Polite Email | Official Crossref metadata API; open access with Polite pool rate of 50 requests/sec via `mailto` header. | true |
| `academic_search` | Semantic Scholar | author, paper title, DOI | Tier 3 | Free API Key | Allen Institute for AI Academic Graph API; free self-service API key provides dedicated 1 RPS and batch endpoints (up to 500 papers/call). | true |
| `academic_search` | arXiv API | author, title, category, id | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `academic_search` | CORE API | author, title, DOI | Tier 1 / 3 | None / Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `research_discovery` | EPO OPS | publication/app number, applicant | Tier 3 | Free Consumer Key & Secret | Open Patent Services; free non-paying developer account (`developers.epo.org`) with up to 4 GB/week data quota. | true |
| `research_discovery` | Google Patents Public Datasets | patent number, inventor, assignee | Tier 1 / 3 | Free GCP Account | Google BigQuery dataset `bigquery-public-data.google_patents`; 1 TiB free query processing per month via BigQuery free tier. | true |
| `research_discovery` | Unpaywall API | DOI, email | Tier 1 | None (Polite `email` param) | Open database of open-access scholarly links; unauthenticated open query up to 100,000 calls/day via `?email=` parameter. | true |
| `research_discovery` | OpenAIRE Graph API | title, author, DOI | Tier 1 / 3 | None / Free Bearer Token | European open science index; provides 60 req/hr unauthenticated and up to 7,200 req/hr with free Personal Access Token. | true |
| `social_username` | OWASP SocialOSINTLM | username | Tier 3 | Platform Keys + LLM Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_username` | Masto | username, instance | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_username` | Octosuite | username, org, repo | Tier 1 | None / Optional GH Token | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_username` | scrawler | username, URL | Tier 2 | None / User Cookies | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_profile` | CrossLinked | company name | Tier 2 | None | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_profile` | Slinky | URL | Tier 1 | None (Offline parser) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_profile` | tiktok-hashtag-analysis | hashtag | Tier 2 | None | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `social_profile` | Zehef | email | Tier 2 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `darkweb_search` | OnionSearch | keyword | Tier 4 | None (Optional Tor proxy) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `darkweb_search` | TorBot | URL, keyword | Tier 4 | None (Tor SOCKS proxy) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `darkweb_search` | Piano (darknet-crawler) | keyword | Tier 4 | None (Offline aggregator) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `darkweb_search` | Intelligence X | email, domain, IP, hash | Tier 4 | Free API Key (`x-key`) | Official REST API (`2.intelx.io`); free registered key allows up to 50 selector searches per day across darknet/leak indexes. | true |
| `crypto_blockchain` | mempool.space API | BTC address, txid | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `crypto_blockchain` | Blockstream Esplora | BTC address, txid | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `crypto_blockchain` | Blockchair API | address, txid | Tier 1 | None / Free Key | Multi-chain explorer API (BTC, ETH, BCH, LTC, DOGE); unauthenticated tier provides 1,000 free requests per day. | true |
| `crypto_blockchain` | Etherscan API V2 | EVM address, txid | Tier 3 | Free API Key | Unified V2 multi-chain gateway (`api.etherscan.io/v2/api?chainid=...`); free self-service key grants 3 RPS and up to 100,000 calls/day. | true |
| `crypto_blockchain` | BlockCypher | address, txid | Tier 1 / 3 | None / Free API Token | Multi-currency API (BTC, ETH, LTC, DOGE); permanent recurring free tier provides 1,000 requests/day, 100 req/hr, and 3 req/sec. | true |
| `crypto_blockchain` | Chainabuse | address, URL | Tier 3 | Free Registered Key | Powered by TRM Labs; free registered API key allows recurring monthly malicious wallet checks; Partner Program provides 5,000 req/hr. | true |
| `technical_surface_search` | GitLab Search API | keyword, code snippet | Tier 1 / 3 | Free Token / None | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `technical_surface_search` | Debian Code Search API | keyword, package | Tier 3 | Free API Key (`x-dcs-apikey`) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `technical_surface_search` | PublicWWW API | keyword, source-code snippet | Tier 3 | Free API Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `technical_surface_search` | checkdmarc | domain, DNS records | Tier 1 | None (Direct DNS query) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `technical_surface_search` | scan.mx API | domain, DNS records | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `search_engines` | SearXNG | keyword, domain, URL | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `search_engines` | Marginalia Search API | keyword, URL | Tier 1 / 3 | Free Public / Email Key | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `search_engines` | Google Custom Search JSON API | keyword | Tier 3 | Free Google Cloud Key | Provides permanent free recurring tier of 100 queries/day without requiring billing account (note: scheduled sunset Jan 2027). | true |
| `search_engines` | Common Crawl Index API | URL, domain | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | Qualys SSL Labs API | domain, hostname, IP | Tier 1 | None (Unauthenticated) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | testssl.sh | domain, hostname, IP, port | Tier 1 | None (Direct TLS probe) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | CipherScan | domain, hostname, IP, port | Tier 1 | None (Direct TLS probe) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | CertGraph | domain, hostname, IP | Tier 1 | None (Queries public CT) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | sslscan | domain, hostname, IP, port | Tier 1 | None (Direct TLS probe) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |
| `ssl_tls` | tlsx | domain, hostname, IP, CIDR, ASN | Tier 1 | None (Direct TLS handshake) | unknown — no explicit numeric quota in recovered verification notes; confirm official limit before implementation | true |

## One-off adapters

These nine accepted candidates remain separate because their specialized invocation or evidence model does not fit the planned shared schemas without obscuring source-specific behavior. Each still needs its own manifest entry, Dockerfile, parser, fixture, tests, and capture case if implemented.

| candidate | category | input types | legal tier | reason to keep separate |
| --- | ---: | --- | ---: | --- |
| crypttrace | 5 | wallet address | Tier 1 | Standalone wallet-flow/risk analysis with a distinct graph-oriented output. |
| DFIT | 4 | image | Tier 1 | Specialized image forensics; keep its image-analysis evidence separate from geolocation lookup results. |
| steg-analyzer | 4 | image | Tier 1 | Specialized steganography analysis output. |
| ShadowFinder Web | 4 | image, date/time | Tier 1 | Specialized shadow/solar geolocation evidence. |
| pybdshadow | 4 | buildings, datetime | Tier 1 | Specialized building-shadow geometry output. |
| youtube-geofind | 4 | coordinates, channel | Tier 3 | Video geolocation workflow with distinct evidence and input handling. |
| GeoLocator | 4 | image, video | Tier 1 | Dedicated geolocation inference output. |
| Betaface | 4 | face image | Tier 3 | Image-based face matching output, with a distinct schema and review requirements. |
| VENOM | 3 | email, username, phone, domain | Tier 2 | Specialized leak-checking workflow with a distinct source/output contract. |

One-off estimate: **9 sessions** (1 session per one-off). Estimated total for this plan: **51 sessions** (42 composite + 9 one-off sessions).

## Coverage check

- Accepted candidates in verification source: **111**.
- Assigned once to a composite or one-off: **111**.
- Composite adapters: **21**, each with 4–6 sub-sources.
- One-off adapters: **9**.
- Unassigned, duplicate, or non-ACCEPT candidates: **0**.

All sub-source names and input types above come from the ACCEPT rows in `docs/VERIFICATION_COMPLETE.md`. This plan does not change the manifest or implement any adapter.
