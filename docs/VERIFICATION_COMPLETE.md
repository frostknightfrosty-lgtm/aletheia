# OSINT Candidate Verification — Complete

**Session date:** 2026-10-12  
**Total candidates:** 187  
**Accepted:** 111 (59.4%)  
**Deferred:** 7 (3.7%)  
**Rejected:** 69 (36.9%)

## Source and limitations

This document transcribes the candidate-level verification tables emitted in the prior Gemini session transcript. The tables were recovered from transcript records for categories 15, 6, and 4 (step 271); categories 8, 3, and 7 (step 358); and categories 9, 1, 5, 11, 10, 14, 13, 12, and 2 (step 599). The tables below preserve those results; they were not independently re-verified in this session.

The ACCEPT/DEFER/REJECT verdicts describe candidate suitability as recorded by that session. ACCEPT does not mean an Aletheia adapter is implemented, CI-tested, or verified-live. Treat hosted API terms, rates, availability, and package maintenance as point-in-time details to check again before implementation.

## Category 1 — Social Media

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **OWASP SocialOSINTLM** | `username` | Python CLI / Docker | Platform Keys + LLM Key | MIT License | Active (104 stars, pushed Apr 2026) | Tier 3 | **ACCEPT** | Maintained as OWASP Social OSINT Agent (`bm-github/owasp-social-osint-agent`); aggregates multi-platform public data via official APIs. |
| **1** | **Snoop** | `username` | Python CLI | None | Proprietary EULA (Restricted) | Active (4,043 stars, Oct 2026) | Tier 2 | **REJECT** | `RESTRICTED_SCOPE`: Restrictive non-free license (custom Russian EULA restricts usage to personal use only; forbids redistribution and integration). |
| **1** | **NetSoc_OSINT** | `username` | Python Script | None | GPL-3.0 | Stale (Pushed Sep 2023) | Tier 2 | **REJECT** | `UNMAINTAINED_TOY`: Abandoned > 3 years without commits or updates (last pushed September 2023). |
| **1** | **Zehef** | `email` | Python CLI | None (Unauthenticated) | GPL-3.0 | Active (1,093 stars, Nov 2024) | Tier 2 | **ACCEPT** | Standalone Python OSINT tool to determine registered online accounts for a target email address; active within 24 months. |
| **1** | **SnapchatUsernameChecker** | `username` | Python Script | None | MIT License | Stale (55 stars, Jan 2023) | Tier 2 | **REJECT** | `UNMAINTAINED_TOY`: Abandoned > 3.5 years (last pushed January 2023); 55-star toy script. |
| **1** | **scrawler** | `username`, `URL` | Python CLI | None / User Cookies | GPL-3.0 | Active (2,211 stars, Sep 2026) | Tier 2 | **ACCEPT** | Media downloader and crawler across public social networks (Twitter, Reddit, Mastodon, YouTube); active release cycle. |
| **1** | **Slinky** | `URL` | Go Library | None (Offline parser) | BSD-3-Clause | Active (Pushed Mar 2026) | Tier 1 | **ACCEPT** | Deterministic Go library (`FurqanSoftware/slinky`) for parsing and validating social media profile and content URLs across 20+ networks. |
| **1** | **Masto** | `username`, `instance` | Python CLI / PyPI package | None (Unauthenticated) | MIT License | Active (273 stars, Apr 2025) | Tier 1 | **ACCEPT** | PyPI package `masto`; queries Mastodon and Fediverse instances unauthenticated for account correlation and metadata. |
| **1** | **Octosuite** | `username`, `org`, `repo` | Python CLI / PyPI package | None / Optional GH Token | MIT License | Active (1,896 stars, Sep 2026) | Tier 1 | **ACCEPT** | Maintained under Bellingcat repository (`bellingcat/octosuite`); PyPI v5.1.0; comprehensive GitHub OSINT enumeration. |
| **1** | **CrossLinked** | `company name` | Python CLI | None | GPL-3.0 | Active (1,609 stars, Nov 2024) | Tier 2 | **ACCEPT** | LinkedIn employee enumeration tool using search engine scraping; requires no LinkedIn account or credentials; active within 24 months. |
| **1** | **Discord History Tracker** | `channel/server` | .NET Desktop App / Bookmarklet | User Discord Token | MIT License | Active (589 stars, Jan 2026) | Tier 5 risk | **REJECT** | `NO_DEVELOPER_API`: Interactive GUI (.NET 9) + browser bookmarklet designed for interactive chat saving; no headless CLI/library. |
| **1** | **Who Posted What** | `keyword`, `FB UID` | Web Search Form | N/A (Web UI) | Free Web Utility | Active (200 OK) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Web-based form that generates Facebook search URLs for human browser navigation; no programmatic REST API. |
| **1** | **Social Searcher** | `keyword`, `username` | Hosted REST API | Paid Commercial Key | Commercial Terms | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: No permanent free API key via self-service registration; public search is web-only; API access requires commercial subscription. |
| **1** | **tiktok-hashtag-analysis** | `hashtag` | Python CLI / PyPI package | None | MIT License | Active (377 stars, Jun 2024) | Tier 2 | **ACCEPT** | Bellingcat library (`tiktok-hashtag-analysis` on PyPI); downloads and structures post metadata for TikTok hashtags. |
| **1** | **drawrowfly tiktok-scraper** | `username`, `hashtag` | Node / Python Script | None | None (Unlicensed) | Stale (Pushed May 2023) | Tier 2 | **REJECT** | `UNMAINTAINED_TOY`: Abandoned > 3 years without maintenance (pushed May 2023); missing declared license. |
| **1** | **Apify Social Media Finder** | `username` | Apify Actor | Paid Apify Account | Commercial Pay-per-use | Active (Paid only) | Tier 3 | **REJECT** | `PAID_ONLY`: Commercial pay-per-result actor charging metered usage against prepaid Apify account balances. |
| **1** | **Apify Username Checker** | `username` | Apify Actor | Paid Apify Account | Commercial Pay-per-use | Active (Paid only) | Tier 3 | **REJECT** | `PAID_ONLY`: Commercial pay-per-use actor ($3.25 per 1,000 checks) requiring paid platform credits. |
| **1** | **tyranroot/User-Osint** | `username` | Python Script | None | None (Unlicensed) | Stale (2 stars, May 2026) | Tier 2 | **REJECT** | `UNMAINTAINED_TOY`: 2-star hobby tool; lacks declared open-source license; duplicates Maigret/Sherlock without tests. |

## Category 2 — Dark Web

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2** | **OnionSearch** | `keyword` | Python CLI | None (Optional Tor proxy) | GPL-3.0 | Active (1,816 stars, Aug 2024) | Tier 4 | **ACCEPT** | Standalone Python CLI (`megadose/OnionSearch`); aggregates results across darknet search engines (Ahmia, Torch, Candle). |
| **2** | **TorBot** | `URL`, `keyword` | Python CLI / Docker | None (Tor SOCKS proxy) | GPL-3.0 | Active (5,046 stars, Oct 2026) | Tier 4 | **ACCEPT** | Dark web OSINT crawler (`DedSecInside/TorBot`); collects page titles, emails, and active links from .onion hidden services. |
| **2** | **Ahmia** | `keyword` | Web Search Portal | N/A (Web UI) | Open / Ahmia Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: No public JSON search API endpoint; web search portal only (underlying engines queried via OnionSearch). |
| **2** | **Piano (darknet-crawler)** | `keyword` | Python CLI / Library | None (Offline aggregator) | MIT License | Active (PyPI v0.1.2, Aug 2026) | Tier 4 | **ACCEPT** | DarkNet Crawler (`darknet-crawler` on PyPI); standalone defensive dark-web search aggregator and threat-intel tooling. |
| **2** | **Intelligence X** | `email`, `domain`, `IP`, `hash` | Hosted REST API | Free API Key (`x-key`) | Free Community Terms | Active (200 OK with key) | Tier 4 | **ACCEPT** | Official REST API (`2.intelx.io`); free registered key allows up to 50 selector searches per day across darknet/leak indexes. |

## Category 3 — Leak Checkers

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DeHashed** | `email`, `username`, `ip`, `phone`, `name` | Hosted REST API | Paid Subscription Key | Proprietary Commercial | Active (200 OK) | Tier 4 | **REJECT** | `PAID_ONLY`: Requires active paid subscription ($5.49/week to $19.99/mo); free tier masks all results. |
| **Snusbase** | `email`, `username`, `ip`, `hash` | Hosted REST API | Paid Auth Token | Proprietary Commercial | Active (401 Auth Required) | Tier 4 | **REJECT** | `PAID_ONLY`: Paid-only breach query service ($20+/mo or per-request credits); no free API tier. |
| **BreachDirectory** | `email`, `username`, `domain` | Hosted REST API (RapidAPI) | Free RapidAPI Key | RapidAPI Freemium Terms | Active (200 OK) | Tier 4 | **ACCEPT** | Basic free tier provides 10 requests/month with free RapidAPI subscription; returns breach indicator and SHA-1 password hashes. |
| **Leak-Lookup** | `email`, `username`, `ip`, `phone`, `password` | Hosted REST API | Free Public API Key | Free Registered Terms | Active (200 OK) | Tier 4 | **ACCEPT** | Free public API key granted upon registration (`/api/search`); safely returns breach names only (sensitive fields omitted). |
| **LeakIX** | `domain`, `ip`, `keyword` | Hosted REST API | Free Registered Key | Free Community Terms | Active (200 OK) | Tier 4 | **ACCEPT** | Public index of exposed services and database leaks; free registered API key allows 3,000 requests/month (`api-key: <key>`). |
| **GrayhatWarfare** | `keyword`, `file extension` | Hosted REST API | Free Access Token | Free Account Terms | Active (200 OK) | Tier 2 | **ACCEPT** | Search engine for publicly exposed AWS S3, Azure Blob, and GCP storage buckets; free API access token provided on signup. |
| **HIBP Stealer-log Endpoints** | `email`, `domain` | Hosted REST API | Paid Enterprise Key | Commercial (Pwned 5+) | Active (Paid only) | Tier 4 | **REJECT** | `PAID_ONLY`: Stealer log endpoints are strictly restricted to enterprise Pwned 5+ subscribers ($465+/month). |
| **Bron Vault** | `local log files` | CLI / Docker Dashboard | None (Local execution) | Apache-2.0 License | Active (101 stars, Jun 2026) | Tier 4 | **ACCEPT** | Open-source parser and analysis dashboard for local stealer log dumps (RedLine, Vidar, Racoon); offline execution. |
| **VENOM** | `email`, `username`, `phone`, `domain` | Python CLI Tool | None / Optional Keys | MIT License | Active (Pushed Jun 2026) | Tier 2 | **ACCEPT** | Terminal-based OSINT footprint aggregator querying 25+ free services for email, domain, and account exposures. |

## Category 4 — Image and Geolocation

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PicImageSearch** | `image file`, `url` | Python Lib / CLI | Dependent on engine | MIT License | Active (730 stars, pushed Oct 2026) | Tier 2 | **ACCEPT** | Reverse image search aggregator for Google, SauceNAO, IqDB, Yandex, Bing, Ascii2d. |
| **Lenso.ai API** | `face image` | Hosted REST API | Paid Developer Plan | Proprietary Terms | Active (200 OK) | Tier 3 | **REJECT** | API requires paid Developer subscription; no free API tier. |
| **FaceCheck.ID** | `face image` | Hosted REST API | Paid Crypto Credits | Proprietary Terms | Active (200 OK) | Tier 3 | **REJECT** | Pay-as-you-go crypto credits only ($0.30/search); testing mode only queries 100k dummy faces. |
| **Search4Faces API** | `face image` | Hosted REST API | Paid Account Credits | Proprietary Terms | Active (Paid only) | Tier 3 | **REJECT** | Paid-only credit system for VK/OK face search; no permanent free tier. |
| **GeoSeer API** | `image`, `video` (misclassified) | Hosted REST API | Paid Pro Subscription | Proprietary Terms | Active (403 / typo in URL) | Tier 3 | **REJECT** | Spatial GIS service (WMS/WFS maps), not image/video OSINT; paid-only commercial plans. |
| **Mapillary API v4** | `coordinates`, `bbox` | Hosted REST API | Free Client Token | Meta / Mapillary Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Street-level imagery and detection data; free developer token on mapillary.com. |
| **tracelines** | `bbox` | Python Lib / PyPI | None | Open Bellingcat source | Active (v0.2.0 on PyPI) | Tier 1 | **ACCEPT** | Bellingcat library to extract street-level coverage lines for Google Street View and Mapillary. |
| **Nominatim/Photon (`geoaddress`)** | `place`, `coordinates` | Python Lib / PyPI | None (Unauthenticated) | Open Source | Active (v1.0.3 on PyPI) | Tier 1 | **ACCEPT** | Python wrapper for OpenStreetMap Nominatim and Komoot Photon geocoding services. |
| **Weather-Data-Aggregator** | `coordinates`, `date range` | Python Script / Repo | Third-party Key | MIT License | Stale (0 stars, pushed Dec 2025) | Tier 1 | **REJECT** | 0-star hobby wrapper; requires user Visual Crossing key; prefer direct Open-Meteo API. |
| **Copernicus Data Space** | `bbox`, `date` | Hosted REST / STAC API | Free Registered Account | EU Open Science / Copernicus | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Free access to Sentinel-1/2/3/5P satellite imagery via STAC and OData APIs. |
| **DFIT** | `image` | CLI / PyPI package | None (Offline) | MIT License | Active (v1.0.0 on PyPI) | Tier 1 | **ACCEPT** | Comprehensive command-line image forensics toolkit (EXIF, Error Level Analysis, noise analysis). |
| **steg-analyzer** | `image` | CLI / PyPI package | None (Offline) | MIT License | Active (v1.0.1 on PyPI) | Tier 1 | **ACCEPT** | All-in-one steganography detection and hidden payload extraction tool. |
| **FotoForensics** | `image` | Web Only | N/A (Web UI) | Proprietary Terms | Active (Web only) | Tier 2 | **REJECT** | Web-only ELA analysis with no public free API; DFIT already provides local ELA analysis. |
| **ShadowFinder Web** | `image`, `date/time` | Python / Streamlit Repo | None (Offline) | MIT License | Active (Pushed Sep 2026) | Tier 1 | **ACCEPT** | Geolocation estimation tool calculating sun azimuth and shadow geometry. |
| **pybdshadow** | `buildings`, `datetime` | Python Lib / PyPI | None (Offline) | BSD License | Active (v0.3.5 on PyPI) | Tier 1 | **ACCEPT** | Python library generating building shadow geometry and solar simulation from building footprints. |
| **youtube-geofind** | `coordinates`, `channel` | Python Repo | YouTube Data API Key | MIT License | Active (159 stars, pushed Aug 2026) | Tier 3 | **ACCEPT** | Searches for geotagged YouTube videos within a geographical radius using YouTube API. |
| **GeoLocator** | `image`, `video` | Python Repo | None (Offline) | MIT License | Active (16 stars, pushed Oct 2026) | Tier 1 | **ACCEPT** | Neural network computer vision tool predicting coordinates from visual landscape features. |
| **SightPoint AI** | `image`, `video` | Python Repo | Paid Gemini API Key | None (No license declared) | Stale (2 stars, Jul 2026) | Tier 3 | **REJECT** | Simple LLM prompt wrapper calling Gemini multimodal API; no standalone algorithm or declared license. |
| **Google Street View Static API** | `coordinates` | Hosted REST API | Paid Google Cloud Key | Google Cloud Terms | Active (Paid only) | Tier 3 | **REJECT** | Paid-only cloud service ($0.007/req) requiring GCP billing account; Mapillary provides open coverage. |
| **Betaface** | `face image` | Hosted REST API | Free API Key & Secret | Evaluation Free Tier | Active (200 OK) | Tier 3 | **ACCEPT** | Facial detection and recognition API offering free evaluation tier (up to 500 images/day). |

## Category 5 — Crypto and Blockchain

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **5** | **mempool.space API** | `BTC address`, `txid` | Hosted REST API | None (Unauthenticated) | GPL-3.0 / Public API | Active (200 OK) | Tier 1 | **ACCEPT** | Open, unauthenticated Bitcoin blockchain API; returns balances, UTXOs, historical transactions, fee estimates, and block stats. |
| **5** | **Blockstream Esplora** | `BTC address`, `txid` | Hosted REST API | None (Unauthenticated) | AGPL-3.0 / Public API | Active (200 OK) | Tier 1 | **ACCEPT** | Official Esplora API (`blockstream.info/api/`); open unauthenticated access for Bitcoin and Liquid network addresses and transactions. |
| **5** | **Blockchair API** | `address`, `txid` | Hosted REST API | None / Free Key | Free Community Terms | Active (200 OK) | Tier 1 | **ACCEPT** | Multi-chain explorer API (BTC, ETH, BCH, LTC, DOGE); unauthenticated tier provides 1,000 free requests per day. |
| **5** | **Etherscan API V2** | `EVM address`, `txid` | Hosted REST API | Free API Key | Free Developer Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Unified V2 multi-chain gateway (`api.etherscan.io/v2/api?chainid=...`); free self-service key grants 3 RPS and up to 100,000 calls/day. |
| **5** | **crypttrace** | `wallet address` | Python CLI / PyPI package | None | MIT License | Active (Pushed Sep 2026) | Tier 1 | **ACCEPT** | Standalone Python OSINT tool (`crypttrace` on PyPI); maps fund movements, scores risk, and flags sanctioned/mixer wallets. |
| **5** | **Bitquery** | `address` | Hosted GraphQL API | Paid Subscription Key | Commercial Terms | Active (Trial only) | Tier 3 | **REJECT** | `PAID_ONLY`: 7-day temporary trial only; permanent programmatic usage requires paid subscription ($29–$49+/mo). |
| **5** | **BlockCypher** | `address`, `txid` | Hosted REST API | None / Free API Token | Free Developer Terms | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Multi-currency API (BTC, ETH, LTC, DOGE); permanent recurring free tier provides 1,000 requests/day, 100 req/hr, and 3 req/sec. |
| **5** | **Chainabuse** | `address`, `URL` | Hosted REST API | Free Registered Key | Free Community Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Powered by TRM Labs; free registered API key allows recurring monthly malicious wallet checks; Partner Program provides 5,000 req/hr. |

## Category 6 — Corporate/Legal/Financial/Sanctions

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Companies House API** | `company name`, `company number`, `officer name` | Hosted REST API | Free API Key | Open Government (UK) | Active (200 OK) | Tier 3 | **ACCEPT** | Official UK corporate registry; free API key, 600 req/5min rate limit. |
| **German Handelsregister** | `company name`, `register number` | Web Portal Search | N/A (Web session) | Public Records (Germany) | Active (Web only) | Tier 2 | **REJECT** | No public developer API; web portal with anti-bot CAPTCHA protections. |
| **Data INPI RNE** | `company name`, `siren/siret` | Hosted REST API | Free Portal Key / Open API | Open License (France) | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Official French RNE open data available via `recherche-entreprises.api.gouv.fr` and INPI portal. |
| **KVK Business Register API** | `company name`, `kvk number` | Hosted REST API | Free Developer Key | Open / KVK Terms (Netherlands) | Active (200 OK) | Tier 3 | **ACCEPT** | Official Dutch Chamber of Commerce developer portal; test key provided on registration. |
| **ASIC Registry APIs** | `company name`, `acn/abn` | Hosted REST API | Free GUID Key | Commonwealth of Australia | Active (200 OK) | Tier 3 | **ACCEPT** | ABR WebServices (`abr.business.gov.au/Tools/WebServices`) provides free ABN/ACN corporate queries. |
| **NZBN API** | `company name`, `nzbn` | Hosted REST API | Free API Key | Open Government (NZ) | Active (200 OK) | Tier 3 | **ACCEPT** | Official New Zealand Business Number API via `api.business.govt.nz`; free developer subscription. |
| **CIPC / BizPortal** | `company name`, `enterprise number` | Hosted REST API | OAuth 2.0 Credentials | CIPC Terms (South Africa) | Active (200 OK) | Tier 3 | **ACCEPT** | CIPC APIVerse Hub (`developer.cipc.co.za`) exposes official read-only Companies API. |
| **Judyrecords API** | `person name`, `case number` | Hosted REST API | Custom Approval Required | Private / Proprietary | Active (Inquiry only) | Tier 3 | **DEFER** | Nationwide US docket index; API access requires direct inquiry to `api@judyrecords.com`. |
| **Trellis API** | `person name`, `case number` | Hosted REST API | Paid Enterprise Key | Commercial Terms | Active (Sales-gated) | Tier 3 | **REJECT** | State trial court records platform; commercial enterprise sales-gated API with no free tier. |
| **PACER Case Locator API** | `person name`, `case number` | Hosted REST API | Government Account Auth | Administrative Office of US Courts | Active (200 OK) | Tier 3 | **DEFER** | Access incurs potential billing liability if quarterly usage exceeds $30 waiver limit; CourtListener already integrated. |
| **FINRA BrokerCheck** | `person name`, `crd number` | Web JSON API | None (Unauthenticated) | FINRA Terms | Active (200 OK) | Tier 2 | **ACCEPT** | Unauthenticated public search API endpoint (`api.brokercheck.finra.org/search/individual`) returns broker details. |
| **FDIC BankFind Suite API** | `bank name`, `institution id` | Hosted REST API | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Unauthenticated public REST API (`banks.data.fdic.gov/api/institutions`) for US banks and branches. |
| **Federal Reserve Enforcement Actions** | `person name`, `bank name` | Static JSON Feed | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Public structured JSON dataset (`ea-old.json` / `ea-cms-recent.json`) of enforcement orders and banks. |
| **OCC Enforcement Actions Search** | `bank name`, `person name` | Web Form Query | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Public web query (`apps.occ.gov/EASearch/?q=...`) returning parseable HTML tables of OCC enforcement orders. |
| **UK Sanctions List** | `person name`, `entity name` | Downloadable CSV/JSON | None (Unauthenticated) | Open Government Licence | Active (200 OK) | Tier 1 | **ACCEPT** | Official FCDO / OFSI consolidated sanctions data available in machine-readable open formats. |
| **Swiss SECO Sanctions List** | `person name`, `company name` | Downloadable XML/JSON | None (Unauthenticated) | Swiss Confederation Open Data | Active (200 OK) | Tier 1 | **ACCEPT** | State Secretariat for Economic Affairs daily updated consolidated sanctions export. |
| **EU Consolidated Sanctions** | `person name`, `organisation name` | Downloadable XML/CSV | None (Unauthenticated) | European Union Open Data | Active (200 OK) | Tier 1 | **ACCEPT** | European Commission official financial sanctions list available in structured XML/CSV formats. |
| **USAspending API** | `company name`, `recipient id` | Hosted REST API | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Completely open public REST API (`api.usaspending.gov/api/v2/`) for federal contracts, grants, and recipients. |
| **SAM.gov APIs** | `company name`, `uei`, `cage code` | Hosted REST API | Free API Key (`api.data.gov`) | Public Domain (US Gov) | Active (200 OK) | Tier 3 | **ACCEPT** | GSA official entity management and exclusion list API; free API key from `api.data.gov`. |
| **Lobbying Disclosure Act API** | `lobbyist name`, `organisation` | Hosted REST API | Anonymous / Free Token | Public Domain (US Gov) | Active (Moved to `lda.gov`) | Tier 1 / 3 | **ACCEPT** | Migrated to `lda.gov/api/v1/`; provides 15 req/min anonymous access and free token registration for 120 req/min. |
| **FollowTheMoney API** | `donor name`, `candidate` | Hosted REST API | Free API Key | OpenSecrets Terms | Active (200 OK) | Tier 3 | **ACCEPT** | OpenSecrets / National Institute on Money in Politics API for state and federal campaign contributions. |

## Category 7 — Government and Public Records

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MuckRock API** | `agency`, `person name` | Hosted REST API | User Account Token | Open Access Terms | Active (401 Token Req) | Tier 3 | **DEFER** | FOIA request tracking API; requires account token; explicitly deferred in Aletheia documentation pending access contract verification. |
| **FOIA.gov API** | `agency`, `office` | Hosted REST API | Free API Key (`api.data.gov`) | Public Domain (US Gov) | Active (200 OK via `api.foia.gov`) | Tier 3 | **ACCEPT** | Official DOJ FOIA portal API (`api.foia.gov/api/agency_components`); free API key from `api.data.gov`. |
| **Regrid Parcel API** | `owner name`, `address`, `parcel number` | Hosted REST API | Paid Subscription Key | Proprietary Commercial | Active (Trial only) | Tier 3 | **REJECT** | `PAID_ONLY`: 30-day sandbox trial only; permanent usage requires paid monthly subscription ($100+/mo). |
| **ReportAll USA Parcel API** | `owner name`, `address`, `county` | Hosted REST API | Prepay Volume Key | Commercial Terms | Active (Trial only) | Tier 3 | **REJECT** | `PAID_ONLY`: 30-day evaluation trial with 1,000 transactions; permanent use requires paid annual prepay volume packages. |
| **NHTSA vPIC** | `vin` | Hosted REST API | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Vehicle Product Information Catalog API (`vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}`); decodes vehicle specs without auth. |
| **Federal BOP Inmate Locator** | `name`, `register number` | Web JSON API | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Unauthenticated public JSON endpoint (`bop.gov/PublicInfo/execute/inmateloc?todo=query&output=json`) returning inmate location and release dates. |
| **ICE Online Detainee Locator** | `name`, `a-number` | Web Portal Form | N/A (Web session) | DHS / ICE Terms | Active (CAPTCHA gated) | Tier 5 risk | **REJECT** | `NO_DEVELOPER_API`: No public REST API; web application protected by anti-bot challenge controls (bypassing triggers Tier 5). |
| **Florida Voter Extract** | `name`, `county` | Statutory Disk / SFTP Form | Application / Statutory Fee | Fla. Stat. § 97.0585 | Active (403 / Form only) | Tier 3 | **REJECT** | `NO_DEVELOPER_API`: Statutory request procedure for monthly voter files; distributed via physical media or SFTP order form. |
| **NYC Open Data API** | `person name`, `date`, `location` | Hosted REST (SODA API) | None / Free App Token | Public Domain (NYC Gov) | Active (200 OK via `data.cityofnewyork.us`) | Tier 1 | **ACCEPT** | Thousands of municipal datasets (licenses, 311 complaints, property records) accessible via open SODA REST endpoints. |
| **County Assessor / Recorder Datasets** | `jurisdiction-specific` | Fragmented Portals | N/A | Local County Rules | Fragmented | N/A | **REJECT** | `NO_DEVELOPER_API`: Vague candidate; over 3,000 US counties with disparate web search interfaces and no unified developer API. |
| **State DOC Inmate Portals** | `state-specific` | Fragmented Portals | N/A | State Corrections Rules | Fragmented | N/A | **REJECT** | `NO_DEVELOPER_API`: Vague candidate; state-specific web portals with varying scrape-hostile bot protections and no unified API. |
| **NSOPW** | `person name`, `location` | Web Search Portal | N/A (Web session) | US DOJ Terms | Active (200 OK / Web only) | Tier 5 risk | **REJECT** | `NO_DEVELOPER_API`: National Sex Offender Public Website has no developer API; web searches are protected by anti-bot CAPTCHA controls. |

## Category 8 — Transport

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OpenSky Network API** | `icao24`, `time`, `bbox` | Hosted REST API | None / Free Key | Academic / Non-commercial | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Public community flight tracking; free anonymous access (~400 req/day) and free registered key (~4,000 req/day). |
| **ADS-B Exchange API** | `icao hex`, `registration`, `callsign` | Hosted REST API (RapidAPI) | Paid Subscription Key | Proprietary Terms (JETNET) | Active (Timed out / Paid) | Tier 3 | **REJECT** | `PAID_ONLY`: No permanent free tier; Basic plan is paid ($10/mo for 10k requests) via RapidAPI. |
| **Aviation Edge API** | `flight number`, `registration` | Hosted REST API | Paid Subscription Key | Proprietary Commercial | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: Commercial API starting at €19–€99+/mo; only temporary ~100-request trial keys on manual request. |
| **FlightAware AeroAPI** | `flight identifier`, `airport` | Hosted REST API | Metered Credit Card Auth | Commercial Terms | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: Mandatory credit card required for registration; uses metered query billing with overage liability. |
| **FAA Aircraft Registration** | `tail number` | Downloadable CSV/ZIP | None (Unauthenticated) | Public Domain (US Gov) | Active (200 OK) | Tier 1 | **ACCEPT** | Daily updated official civil aircraft database (`ReleasableAircraft.zip`); contains N-number, registrant, and engine specs. |
| **IMO GISIS** | `imo number`, `vessel name` | Web Portal Session | N/A (Web Account) | IMO Web Terms | Active (200 OK) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: No public REST/machine-readable API; browser-only portal with daily human search caps. |
| **VesselFinder API** | `vessel name`, `mmsi`, `imo` | Hosted REST API | Paid Credit Packages | Proprietary Terms | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: No free API tier; prepaid credit packages start at €330 for 10,000 credits. |
| **Datalastic API** | `vessel name`, `mmsi`, `imo` | Hosted REST API | Paid Subscription Key | Proprietary Terms | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: No free tier for ongoing API access; requires paid monthly subscription (€9/trial to €29+/mo). |
| **BarentsWatch AIS API** | `mmsi`, `time`, `coordinates` | Hosted Streaming / REST API | Free OAuth 2.0 Credentials | Norwegian Gov Open Data | Active (200 OK via `developer.barentswatch.no`) | Tier 3 | **ACCEPT** | Official Norwegian Coastal Administration live AIS stream & REST endpoints; free OAuth client credentials on developer portal. |
| **MarineTraffic AIS API** | `vessel identifier`, `mmsi` | Hosted REST API | Paid Credit Packages | Proprietary Terms (Kpler) | Active (200 OK) | Tier 3 | **REJECT** | `PAID_ONLY`: Programmatic API requires paid credit bundles or enterprise agreement; free web account lacks API access. |
| **Paris MoU / THETIS** | `vessel name` | Web Portal / XML Feed | Manual Agreement Auth | Paris MoU / EMSA Terms | Active (Web only) | Tier 2 / 3 | **REJECT** | `NO_DEVELOPER_API`: No open REST API; inspection lookups are web-only; bulk XML requires manual data-sharing application. |
| **Tokyo MoU PSC** | `vessel name` | Web Portal Search | None (Web only) | Tokyo MoU Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: No public developer REST API; web lookup portal only (records mirrored via OpenSanctions). |
| **Network Rail Open Data** | `train/service identifier` | STOMP / ActiveMQ / REST | Free Self-service Key | Open Government / Rail Data | Active (200 OK) | Tier 3 | **ACCEPT** | Real-time train movements (TRUST), train describer feeds, and CIF schedules via free developer registration (`data.networkrail.co.uk`). |
| **National Rail Data** | `station`, `service` | SOAP / REST / Push Port | Free Developer Token | RDG Open Data Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Darwin live departure boards (LDBWS) and timetable feeds via free token registration on `opendata.nationalrail.co.uk`. |
| **Deutsche Bahn Timetables API** | `station`, `train`, `date` | Hosted REST API | Free Client-ID & Secret | DB Open Data Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Official Deutsche Bahn developer portal (`developers.deutschebahn.com`); free API keys for station and timetable search. |
| **OpenRailwayMap API** | `station/facility`, `uic` | Overpass QL / Vector Tiles | None (Unauthenticated) | ODbL (OpenStreetMap) | Active (200 OK) | Tier 1 | **ACCEPT** | Queryable worldwide railway infrastructure via Overpass API (`railway=*`) and OpenRailwayMap GeoJSON/tiles. |
| **ERATV** | `vehicle type` | SPARQL / RDF / Linked Data | None (Unauthenticated) | European Union Open Data | Active (200 OK) | Tier 1 | **ACCEPT** | European Register of Authorized Types of Railway Vehicles; accessible via public SPARQL endpoint and Zenodo/EU bulk dumps. |
| **Planespotters API** | `aircraft registration`, `hex` | Hosted REST API | None (Unauthenticated) | Community Free Terms | Active (200 OK) | Tier 1 | **ACCEPT** | Free public JSON endpoint (`api.planespotters.net/pub/photos/reg/{reg}` or `/hex/{hex}`) returning aircraft photos and metadata. |
| **AIS Hub** | `vessel identifier`, `mmsi` | Real-time Feed API | Hardware Feeder Key | Community Feeder Agreement | Active (Feeder-gated) | Tier 3 | **REJECT** | `RESTRICTED_SCOPE`: Operates on a hardware barter model; requires streaming your own physical AIS antenna receiver data. |
| **ICAO 24-bit Database** | `icao hex` | None (Unlocatable) | None | N/A | Unlocatable | N/A | **REJECT** | `NO_DEVELOPER_API`: Vague candidate with no standalone ICAO API; lookups are handled via FAA Releasable and OpenSky Network. |

## Category 9 — Patents and Trademarks

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **9** | **PatentsView** | `patent number`, `inventor`, `assignee` | Hosted REST API | Free API Key | Public Domain / USPTO Open Data | Active (200 OK via `search.patentsview.org`) | Tier 3 | **ACCEPT** | Free self-service API key via USPTO support portal; comprehensive query endpoints (`/api/v1/patent/`, `/assignee/`). |
| **9** | **USPTO Open Data Portal** | `patent`, `trademark` | Hosted REST API | Free API Key | Public Domain (US Gov) | Active (200 OK via `developer.uspto.gov`) | Tier 3 | **ACCEPT** | Free developer account on `developer.uspto.gov`; provides Patent Examination Data System (PEDS) and trademark status APIs. |
| **9** | **USPTO Patent Assignment Search** | `patent number`, `assignor`, `assignee` | Hosted REST API | Free API Key | Public Domain (US Gov) | Active (200 OK via `api.uspto.gov`) | Tier 3 | **ACCEPT** | Assignment records migrated to USPTO Open Data Portal (`/api/v1/patent/applications/{id}/assignment`); free developer key. |
| **9** | **USPTO TSDR** | `trademark serial/reg number` | Hosted REST API | Free API Key | Public Domain (US Gov) | Active (200 OK via `developer.uspto.gov`) | Tier 3 | **ACCEPT** | Trademark Status & Document Retrieval API (`developer.uspto.gov/swagger/tsdr-api-v1`); free key via USPTO API Key Manager. |
| **9** | **EPO OPS** | `publication/app number`, `applicant` | Hosted REST API (OAuth 2.0) | Free Consumer Key & Secret | European Patent Office Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Open Patent Services; free non-paying developer account (`developers.epo.org`) with up to 4 GB/week data quota. |
| **9** | **WIPO PATENTSCOPE** | `PCT application number` | Web Search Portal | N/A (Web session) | WIPO Database Terms | Active (200 OK / Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: No public REST API; terms strictly prohibit automated queries and web scraping (>10 req/min banned). |
| **9** | **Lens API** | `inventor`, `applicant`, `identifier` | Hosted REST API | Paid Custom Plan | Commercial Terms (Cambia) | Active (Trial only) | Tier 3 | **REJECT** | `PAID_ONLY`: API access is limited to a one-time 14-day evaluation trial; permanent use requires paid Member/Custom subscription. |
| **9** | **Google Patents Public Datasets** | `patent number`, `inventor`, `assignee` | BigQuery Client / REST API | Free GCP Account | Open Public Data | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Google BigQuery dataset `bigquery-public-data.google_patents`; 1 TiB free query processing per month via BigQuery free tier. |
| **9** | **JPO APIs** | `applicant`, `application number` | Hosted REST API | Ministry Approval Credentials | Japan Patent Office Terms | Active (Trial approval required) | Tier 3 | **DEFER** | Free trial access requires submitting manual registration application via email (`PA0630@jpo.go.jp`) to JPO General Coordination Division. |
| **9** | **WIPO Global Brand Database** | `trademark name`, `owner` | Web Search Portal | N/A (Web session) | WIPO Web Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Web-based search portal only; no developer API tier; terms explicitly prohibit automated querying and robots. |
| **9** | **EUIPO eSearch plus** | `mark/name`, `owner` | Hosted REST API | Free Developer Key / OAuth | EU Open Data / EUIPO Terms | Active (200 OK via `dev.euipo.europa.eu`) | Tier 3 | **ACCEPT** | Official EUIPO Developer Portal provides free Trademark Search & Design Search REST APIs with sandbox and production keys. |
| **9** | **TMview** | `mark name`, `owner` | Web Search Portal | N/A (Web session) | TMDN Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Multi-office web search front-end on `tmdn.org` with no standalone developer API; official EU queries route to EUIPO API. |
| **9** | **DesignView** | `design identifier`, `owner` | Web Search Portal | N/A (Web session) | TMDN Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Web consultation front-end with no standalone developer API; official industrial design queries route to EUIPO API. |
| **9** | **IP India** | `applicant`, `patent number` | Web Search Portal | N/A (Web session) | CGPDTM Terms | Active (CAPTCHA gated) | Tier 5 risk | **REJECT** | `NO_DEVELOPER_API`: No public REST API; web search is protected by custom image CAPTCHAs and OTP barriers (bypass triggers Tier 5). |
| **9** | **CNIPA** | `applicant`, `application number` | Web Search Portal | N/A (Web session) | CNIPA Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: No public self-service developer REST API; M2M access restricted to official institutional international treaty exchanges. |
| **9** | **UK IPO API programme** | `patent number` | Web / Phased Portal | N/A (Unreleased) | Crown Copyright | Active (Phased rollout) | Tier 3 | **REJECT** | `NO_DEVELOPER_API`: Phased One IPO Transformation roadmap; currently lacks an open public developer REST API for live querying. |

## Category 10 — Search Engines

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **10** | **SearXNG** | `keyword`, `domain`, `URL` | Self-hosted / Hosted REST API | None (Unauthenticated) | AGPL-3.0 | Active (Pushed Oct 2026) | Tier 1 | **ACCEPT** | Open-source privacy metasearch engine; exposes standardized JSON search endpoint (`/search?q=...&format=json`); easily containerizable. |
| **10** | **Mojeek API** | `keyword`, `domain`, `URL` | Hosted REST API | Paid Custom Plan | Commercial Terms | Active (Sales-gated) | Tier 3 | **REJECT** | `PAID_ONLY`: No automated self-service free tier; access is price-on-asking (POA) requiring custom contact form quote. |
| **10** | **Marginalia Search API** | `keyword`, `URL` | Hosted REST API | Free Public / Email Key | CC-BY-NC-SA 4.0 | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Independent non-commercial web search engine; provides public test key (`public`) and free personal API keys upon request. |
| **10** | **Brave Search API** | `keyword`, `domain`, `URL` | Hosted REST API | Credit Card Required | Commercial Terms | Active (Metered overage) | Tier 3 | **REJECT** | `PAID_ONLY`: Mandatory credit card entry required for registration; uses automatic metered overage billing liability. |
| **10** | **Google Custom Search JSON API** | `keyword` | Hosted REST API | Free Google Cloud Key | Google Cloud Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Provides permanent free recurring tier of 100 queries/day without requiring billing account (note: scheduled sunset Jan 2027). |
| **10** | **Kagi Search API** | `keyword` | Hosted REST API | Paid Account Credits | Commercial Pay-as-you-go | Active (Paid only) | Tier 3 | **REJECT** | `PAID_ONLY`: Pay-as-you-go commercial credit model ($12 per 1,000 search queries); no free search API tier. |
| **10** | **Common Crawl Index API** | `URL`, `domain` | Hosted REST API (CDX) | None (Unauthenticated) | CC0 / Open Data | Active (200 OK via `index.commoncrawl.org`) | Tier 1 | **ACCEPT** | Public CDX server API querying multi-billion URL web archives by domain/wildcard; completely unauthenticated. |
| **10** | **Whoogle** | `keyword`, `URL` | Python / Docker Repo | None | MIT License | Defunct (Archived Aug 2026) | N/A | **REJECT** | `DEAD_PLATFORM`: Official GitHub repository (`benbusby/whoogle-search`) was permanently archived and sunset by the author. |

## Category 11 — Academic

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **11** | **OpenAlex API** | `author`, `institution`, `DOI` | Hosted REST API | None / Polite Email | CC0 Public Domain | Active (200 OK via `api.openalex.org`) | Tier 1 | **ACCEPT** | Open bibliographic graph indexing 250M+ works; unauthenticated access grants 100,000 calls/day; Polite pool via email header. |
| **11** | **Crossref REST API** | `title`, `author`, `DOI` | Hosted REST API | None / Polite Email | CC0 Public Domain | Active (200 OK via `api.crossref.org`) | Tier 1 | **ACCEPT** | Official Crossref metadata API; open access with Polite pool rate of 50 requests/sec via `mailto` header. |
| **11** | **Semantic Scholar** | `author`, `paper title`, `DOI` | Hosted REST API | Free API Key | Non-profit Research (AI2) | Active (200 OK with key) | Tier 3 | **ACCEPT** | Allen Institute for AI Academic Graph API; free self-service API key provides dedicated 1 RPS and batch endpoints (up to 500 papers/call). |
| **11** | **arXiv API** | `author`, `title`, `category`, `id` | Hosted REST API (Atom XML) | None (Unauthenticated) | Open Access (arXiv Terms) | Active (200 OK via `export.arxiv.org`) | Tier 1 | **ACCEPT** | Open unauthenticated search query endpoint for scientific preprints across physics, computer science, math, and biology. |
| **11** | **CORE API** | `author`, `title`, `DOI` | Hosted REST API | None / Free API Key | Open Access / CORE Terms | Active (200 OK via `api.core.ac.uk`) | Tier 1 / 3 | **ACCEPT** | World's largest open access research aggregator; free unauthenticated search and free developer API key via `core.ac.uk`. |
| **11** | **Unpaywall API** | `DOI`, `email` | Hosted REST API | None (Polite `email` param) | CC0 / Open Access | Active (200 OK via `api.unpaywall.org`) | Tier 1 | **ACCEPT** | Open database of open-access scholarly links; unauthenticated open query up to 100,000 calls/day via `?email=` parameter. |
| **11** | **BASE OAI** | `title`, `author` | OAI-PMH / HTTP API | Manual IP Whitelisting | Non-commercial Academic | Active (IP gated) | Tier 3 | **DEFER** | Bielefeld Academic Search Engine; access to OAI-PMH and HTTP search is free but strictly gated behind manual static IP-whitelisting application. |
| **11** | **Dimensions Analytics API** | `author`, `publication` | Hosted REST API | Paid Enterprise Key | Commercial Terms (Digital Science) | Active (Sales-gated) | Tier 3 | **REJECT** | `PAID_ONLY`: Institutional sales-gated subscription platform with no public self-service free developer tier. |
| **11** | **OpenAIRE Graph API** | `title`, `author`, `DOI` | Hosted REST API | None / Free Bearer Token | CC-BY (European Open Science) | Active (200 OK via `api.openaire.eu`) | Tier 1 / 3 | **ACCEPT** | European open science index; provides 60 req/hr unauthenticated and up to 7,200 req/hr with free Personal Access Token. |

## Category 12 — Paste and Code

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **12** | **Pastebin Developers API** | `text`, `paste ID` | Hosted REST API | Free Dev Key | Commercial / Free Dev | Active (Restricted scope) | Tier 3 | **REJECT** | `RESTRICTED_SCOPE`: Standard developer API only manages user's own pastes; lacks arbitrary search; scraping feed discontinued. |
| **12** | **GitLab Search API** | `keyword`, `code snippet` | Hosted REST API | Free Token / None | GitLab Open API | Active (200 OK via `gitlab.com`) | Tier 1 / 3 | **ACCEPT** | Official GitLab REST API (`/api/v4/search?scope=blobs&search=...`); queries public code repositories across GitLab.com. |
| **12** | **Sourcegraph API** | `keyword`, `code snippet` | Hosted GraphQL API | Enterprise Contract | Commercial Terms | Active (Enterprise gated) | Tier 3 | **REJECT** | `PAID_ONLY`: No public free developer search API; external API access is restricted to enterprise-tier deployments. |
| **12** | **Debian Code Search API** | `keyword`, `package` | Hosted REST API | Free API Key (`x-dcs-apikey`) | DFSG Open Source | Active (200 OK with key) | Tier 3 | **ACCEPT** | Official Debian code search (`codesearch.debian.net/api/v1/search`); free personal API key generated via Debian Salsa account. |
| **12** | **PublicWWW API** | `keyword`, `source-code snippet` | Hosted REST API | Free API Key | Freemium Community Terms | Active (200 OK via `api.publicwww.com`) | Tier 3 | **ACCEPT** | Source code search engine indexing HTML/JS/CSS snippets; free registered API key allows querying top 3M websites. |
| **12** | **NerdyData API** | `code snippet`, `technology` | Hosted REST API | Paid Account Credits | Commercial Pay-as-you-go | Active (Paid only) | Tier 3 | **REJECT** | `PAID_ONLY`: Developer API access operates on a strictly pay-as-you-go commercial credit model. |

## Category 13 — Email Authentication

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **13** | **MXToolbox Lookup API** | `domain`, `IP`, `DKIM selector` | Hosted REST API | Paid Plan Key | Commercial Terms | Active (401 Auth Required) | Tier 3 | **REJECT** | `PAID_ONLY`: Free accounts only receive ~68 one-time test requests; ongoing REST API access requires paid subscription ($129+/mo). |
| **13** | **dmarcian REST API** | `domain`, `DKIM selector` | Hosted REST API | Paid Enterprise Key | Commercial Terms | Active (403 Forbidden) | Tier 3 | **REJECT** | `PAID_ONLY`: Programmatic REST API access is strictly restricted to paid Enterprise tier plans ($499+/month). |
| **13** | **EasyDMARC Public API** | `domain`, `SPF`, `DKIM selector` | Hosted REST API | Paid Enterprise Key | Commercial Terms | Active (404 / Gated) | Tier 3 | **REJECT** | `PAID_ONLY`: REST API access is not included on free accounts; restricted to paid Business/Enterprise tiers. |
| **13** | **checkdmarc** | `domain`, `DNS records` | Python CLI / Library | None (Direct DNS query) | Apache-2.0 | Active (321 stars, Oct 2026) | Tier 1 | **ACCEPT** | PyPI v6.0.3 (`domainaware/checkdmarc`); robust parser and validator for SPF, DMARC, DKIM, and BIMI DNS records. |
| **13** | **scan.mx API** | `domain`, `DNS records` | Hosted REST API | None (Unauthenticated) | Free Public API | Active (200 OK via `api.scan.mx`) | Tier 1 | **ACCEPT** | Free public REST API (`GET https://api.scan.mx/v1/check?domain={domain}`); returns comprehensive JSON report and grade without key. |
| **13** | **MXToolbox Header Analyzer** | `raw email header` | Web Search Form | N/A (Web UI) | Free Web Utility | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Web-only browser utility for pasting email headers; no programmatic developer REST API. |
| **13** | **Google Admin Messageheader** | `raw email header` | Web Search Form | N/A (Web UI) | Google Workspace Terms | Active (Web only) | Tier 2 | **REJECT** | `NO_DEVELOPER_API`: Interactive web browser tool on `toolbox.googleapps.com`; lacks a developer API endpoint. |

## Category 14 — SSL/TLS

| Category | Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **14** | **Qualys SSL Labs API** | `domain`, `hostname`, `IP` | Hosted REST API / Go CLI | None (Unauthenticated) | Apache-2.0 / SSL Labs Terms | Active (200 OK via `api.ssllabs.com`) | Tier 1 | **ACCEPT** | Official v3 REST API and open-source CLI scanner (`ssllabs/ssllabs-scan`); free unauthenticated SSL/TLS assessment. |
| **14** | **Hardenize Organization API** | `domain`, `hostname`, `cert hash` | Hosted REST API | Paid Enterprise Key | Commercial Terms (Red Sift) | Active (Sales-gated) | Tier 3 | **REJECT** | `PAID_ONLY`: Programmatic REST API access is restricted to Business/Enterprise contracts ($5,000+/year) via sales demo. |
| **14** | **testssl.sh** | `domain`, `hostname`, `IP`, `port` | CLI / Shell Script | None (Direct TLS probe) | GPL-2.0 | Active (9,233 stars, Oct 2026) | Tier 1 | **ACCEPT** | Gold-standard command-line tool for auditing TLS/SSL ciphers, protocols, certificate chains, and cryptographic vulnerabilities. |
| **14** | **CipherScan** | `domain`, `hostname`, `IP`, `port` | CLI / Python Wrapper | None (Direct TLS probe) | MPL-2.0 | Active (1,993 stars, Jun 2025) | Tier 1 | **ACCEPT** | Standalone Unix CLI utility (`mozilla/cipherscan`); probes server cipher suite ordering and TLS configurations. |
| **14** | **CertGraph** | `domain`, `hostname`, `IP` | Go CLI / Binary | None (Queries public CT) | GPL-2.0 | Active (383 stars, Oct 2026) | Tier 1 | **ACCEPT** | Open-source intelligence tool (`lanrat/certgraph`) to crawl Certificate Transparency (CT) graphs, mapping subdomains and certificate links. |
| **14** | **sslscan** | `domain`, `hostname`, `IP`, `port` | C CLI Binary | None (Direct TLS probe) | GPL-3.0 | Active (2,633 stars, Sep 2026) | Tier 1 | **ACCEPT** | Fast native binary (`rbsec/sslscan`) querying SSL/TLS enabled services to discover supported cipher suites and server certs. |
| **14** | **tlsx** | `domain`, `hostname`, `IP`, `CIDR`, `ASN` | Go CLI Binary | None (Direct TLS handshake) | MIT License | Active (1,148 stars, Oct 2026) | Tier 1 | **ACCEPT** | Fast, configurable TLS grabber by ProjectDiscovery (`projectdiscovery/tlsx`); extracts certificates, SANs, JARM hashes, and ciphers. |

## Category 15 — IP Intelligence

| Candidate | Input Type | Invocation / Access Type | Auth / Key | License / Terms | Maintenance / Status | Legal Tier | Verdict | Notes / Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **IPinfo API** | `ip`, `asn` | Hosted REST API | Free API Token | Proprietary / Free Community Terms | Active (200 OK) | Tier 3 | **ACCEPT** | 50,000 req/mo free on signup; returns IP geo, ASN, hostname, company org. |
| **IP-API** | `ip`, `domain` | Hosted REST API | None (Unauthenticated) | Non-commercial Free Terms | Active (200 OK) | Tier 1 | **ACCEPT** | 45 req/min free HTTP unauthenticated; IP geolocation & ASN resolution. |
| **ipapi.co** | `ip` | Hosted REST API | None / Free Key | Proprietary Free Tier | Active (200 OK) | Tier 1 | **ACCEPT** | 1,000 req/day (30k/mo) free unauthenticated tier for IP location/network data. |
| **IPGeolocation.io** | `ip`, `domain`, `user-agent` | Hosted REST API | Free API Key | Free Developer Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Free tier provides 1,000 req/day (30,000/mo) for IP geolocation & threat intel. |
| **AbuseIPDB API v2** | `ip`, `cidr` | Hosted REST API | Free API Key | Free Webmaster/Individual Terms | Active (200 OK) | Tier 3 | **ACCEPT** | 1,000 checks/day on free registered account; IP abuse confidence scoring. |
| **GreyNoise Community API** | `ip` | Hosted REST API | Free API Key | Free Community Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Community API provides internet noise, scanning actor classification, riot detection. |
| **VirusTotal API v3** | `ip`, `domain`, `url`, `hash` | Hosted REST API | Free API Key | Free Public API Terms | Active (200 OK) | Tier 3 | **ACCEPT** | 4 req/min, 500 req/day, 15,000 req/mo public API quota for multi-engine detections. |
| **CIRCL Passive DNS** | `ip`, `hostname`, `domain` | Hosted REST API | Trusted Partner Auth | Restricted / CERT CSIRT vetting | Active (Restricted) | Tier 3 | **DEFER** | Access restricted to trusted incident response partners/CSIRTs; no self-serve free key. |
| **CIRCL Passive SSL** | `ip`, `cidr`, `cert fingerprint` | Hosted REST API | Trusted Partner Auth | Restricted / CSIRT vetting | Active (Restricted) | Tier 3 | **DEFER** | Historical X.509 certificate IP mapping; restricted to verified security research partners. |
| **URLhaus Community API** | `url`, `domain`, `ip` | Hosted REST API | Free `Auth-Key` (`auth.abuse.ch`) | Open / abuse.ch Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Public malware URL/IP threat intelligence; requires free abuse.ch auth portal key. |
| **ThreatFox Community API** | `ip`, `domain`, `url`, `hash` | Hosted REST API | Free `Auth-Key` (`auth.abuse.ch`) | Open / abuse.ch Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Community IOC sharing platform; requires free abuse.ch Auth-Key. |
| **MalwareBazaar Community API** | `hash` (`md5`, `sha1`, `sha256`) | Hosted REST API | Free `Auth-Key` (`auth.abuse.ch`) | Open / abuse.ch Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Malware sample & hash query API; requires free abuse.ch Auth-Key. |
| **PhishTank API** | `url` | Hosted REST API | Optional Free `app_key` | Cisco Talos Terms | Active (200 OK) | Tier 1 / 3 | **ACCEPT** | Public phishing verification; optional app_key for higher rate limits. |
| **Censys Platform API** | `ip`, `domain`, `hostname`, `cert` | Hosted REST API | Free API Key (100 credits/mo) | Proprietary Terms | Active (Cloudflare / 403) | Tier 3 | **REJECT** | Excluded integration; removed by project policy due to restrictive 100 credits/mo quota fit. |
| **Netlas API** | `ip`, `cidr`, `domain`, `asn` | Hosted REST API | Free API Key | Free Community Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Community plan grants free API key with 2,500 coins/queries monthly. |
| **FullHunt API** | `domain`, `hostname`, `ip` | Hosted REST API | Free API Key | Free Starter Terms | Active (200 OK) | Tier 3 | **ACCEPT** | Free plan ($0) provides 100 monthly credits for attack surface discovery & IP enumeration. |
| **BinaryEdge Host Search API** | `ip`, `cidr`, `asn` | Hosted REST API | None (Expired) | N/A (Platform sunset) | Defunct / Closed | N/A | **REJECT** | Standalone service acquired by Coalition and permanently shut down March 31, 2025. |
| **ZoomEye API** | `ip`, `domain`, `hostname` | Hosted REST API | Paid Points / Key | Proprietary Commercial Terms | Active (Paid API) | Tier 3 | **REJECT** | Paid-only for programmatic API; free tier quota restricted to manual web UI queries. |
| **HackerTarget API** | `ip`, `domain`, `cidr`, `asn` | Hosted REST API | None (Unauthenticated) | Free Community Terms | Active (200 OK) | Tier 1 | **ACCEPT** | 50 queries/day free unauthenticated for ASN lookup, reverse IP, and ping tools. |
| **ViewDNS.info Reverse IP API** | `ip`, `domain` | Hosted REST API | Free Trial Key (250 calls) | Paid Commercial Terms | Active (Trial only) | Tier 3 | **REJECT** | Only 250 one-time trial queries offered; paid subscription ($29/mo) required thereafter. |
| **ipinfo.app ASN Lookup API** | `asn`, `ip` | Hosted REST API | None (Unauthenticated) | Open API (No tracking) | Active (200 OK) | Tier 1 | **ACCEPT** | Free public REST API (`ip2asn.ipinfo.app/lookup/:ip`); returns ASN and subnet routing without key. |

## Summary statistics

| Category | Candidates | ACCEPT | DEFER | REJECT |
|---|---:|---:|---:|---:|
| Category 1 — Social Media | 18 | 8 | 0 | 10 |
| Category 2 — Dark Web | 5 | 4 | 0 | 1 |
| Category 3 — Leak Checkers | 9 | 6 | 0 | 3 |
| Category 4 — Image and Geolocation | 20 | 12 | 0 | 8 |
| Category 5 — Crypto and Blockchain | 8 | 7 | 0 | 1 |
| Category 6 — Corporate/Legal/Financial/Sanctions | 21 | 17 | 2 | 2 |
| Category 7 — Government and Public Records | 12 | 4 | 1 | 7 |
| Category 8 — Transport | 20 | 9 | 0 | 11 |
| Category 9 — Patents and Trademarks | 16 | 7 | 1 | 8 |
| Category 10 — Search Engines | 8 | 4 | 0 | 4 |
| Category 11 — Academic | 9 | 7 | 1 | 1 |
| Category 12 — Paste and Code | 6 | 3 | 0 | 3 |
| Category 13 — Email Authentication | 7 | 2 | 0 | 5 |
| Category 14 — SSL/TLS | 7 | 6 | 0 | 1 |
| Category 15 — IP Intelligence | 21 | 15 | 2 | 4 |
| **Total** | **187** | **111** | **7** | **69** |

## Section 14 — Full verification table across all categories

| Category | Candidate | Input type | Verdict |
|---|---|---|---|
| 1 — Social Media | **OWASP SocialOSINTLM** | `username` | **ACCEPT** |
| 1 — Social Media | **Snoop** | `username` | **REJECT** |
| 1 — Social Media | **NetSoc_OSINT** | `username` | **REJECT** |
| 1 — Social Media | **Zehef** | `email` | **ACCEPT** |
| 1 — Social Media | **SnapchatUsernameChecker** | `username` | **REJECT** |
| 1 — Social Media | **scrawler** | `username`, `URL` | **ACCEPT** |
| 1 — Social Media | **Slinky** | `URL` | **ACCEPT** |
| 1 — Social Media | **Masto** | `username`, `instance` | **ACCEPT** |
| 1 — Social Media | **Octosuite** | `username`, `org`, `repo` | **ACCEPT** |
| 1 — Social Media | **CrossLinked** | `company name` | **ACCEPT** |
| 1 — Social Media | **Discord History Tracker** | `channel/server` | **REJECT** |
| 1 — Social Media | **Who Posted What** | `keyword`, `FB UID` | **REJECT** |
| 1 — Social Media | **Social Searcher** | `keyword`, `username` | **REJECT** |
| 1 — Social Media | **tiktok-hashtag-analysis** | `hashtag` | **ACCEPT** |
| 1 — Social Media | **drawrowfly tiktok-scraper** | `username`, `hashtag` | **REJECT** |
| 1 — Social Media | **Apify Social Media Finder** | `username` | **REJECT** |
| 1 — Social Media | **Apify Username Checker** | `username` | **REJECT** |
| 1 — Social Media | **tyranroot/User-Osint** | `username` | **REJECT** |
| 2 — Dark Web | **OnionSearch** | `keyword` | **ACCEPT** |
| 2 — Dark Web | **TorBot** | `URL`, `keyword` | **ACCEPT** |
| 2 — Dark Web | **Ahmia** | `keyword` | **REJECT** |
| 2 — Dark Web | **Piano (darknet-crawler)** | `keyword` | **ACCEPT** |
| 2 — Dark Web | **Intelligence X** | `email`, `domain`, `IP`, `hash` | **ACCEPT** |
| 3 — Leak Checkers | **DeHashed** | `email`, `username`, `ip`, `phone`, `name` | **REJECT** |
| 3 — Leak Checkers | **Snusbase** | `email`, `username`, `ip`, `hash` | **REJECT** |
| 3 — Leak Checkers | **BreachDirectory** | `email`, `username`, `domain` | **ACCEPT** |
| 3 — Leak Checkers | **Leak-Lookup** | `email`, `username`, `ip`, `phone`, `password` | **ACCEPT** |
| 3 — Leak Checkers | **LeakIX** | `domain`, `ip`, `keyword` | **ACCEPT** |
| 3 — Leak Checkers | **GrayhatWarfare** | `keyword`, `file extension` | **ACCEPT** |
| 3 — Leak Checkers | **HIBP Stealer-log Endpoints** | `email`, `domain` | **REJECT** |
| 3 — Leak Checkers | **Bron Vault** | `local log files` | **ACCEPT** |
| 3 — Leak Checkers | **VENOM** | `email`, `username`, `phone`, `domain` | **ACCEPT** |
| 4 — Image and Geolocation | **PicImageSearch** | `image file`, `url` | **ACCEPT** |
| 4 — Image and Geolocation | **Lenso.ai API** | `face image` | **REJECT** |
| 4 — Image and Geolocation | **FaceCheck.ID** | `face image` | **REJECT** |
| 4 — Image and Geolocation | **Search4Faces API** | `face image` | **REJECT** |
| 4 — Image and Geolocation | **GeoSeer API** | `image`, `video` (misclassified) | **REJECT** |
| 4 — Image and Geolocation | **Mapillary API v4** | `coordinates`, `bbox` | **ACCEPT** |
| 4 — Image and Geolocation | **tracelines** | `bbox` | **ACCEPT** |
| 4 — Image and Geolocation | **Nominatim/Photon (`geoaddress`)** | `place`, `coordinates` | **ACCEPT** |
| 4 — Image and Geolocation | **Weather-Data-Aggregator** | `coordinates`, `date range` | **REJECT** |
| 4 — Image and Geolocation | **Copernicus Data Space** | `bbox`, `date` | **ACCEPT** |
| 4 — Image and Geolocation | **DFIT** | `image` | **ACCEPT** |
| 4 — Image and Geolocation | **steg-analyzer** | `image` | **ACCEPT** |
| 4 — Image and Geolocation | **FotoForensics** | `image` | **REJECT** |
| 4 — Image and Geolocation | **ShadowFinder Web** | `image`, `date/time` | **ACCEPT** |
| 4 — Image and Geolocation | **pybdshadow** | `buildings`, `datetime` | **ACCEPT** |
| 4 — Image and Geolocation | **youtube-geofind** | `coordinates`, `channel` | **ACCEPT** |
| 4 — Image and Geolocation | **GeoLocator** | `image`, `video` | **ACCEPT** |
| 4 — Image and Geolocation | **SightPoint AI** | `image`, `video` | **REJECT** |
| 4 — Image and Geolocation | **Google Street View Static API** | `coordinates` | **REJECT** |
| 4 — Image and Geolocation | **Betaface** | `face image` | **ACCEPT** |
| 5 — Crypto and Blockchain | **mempool.space API** | `BTC address`, `txid` | **ACCEPT** |
| 5 — Crypto and Blockchain | **Blockstream Esplora** | `BTC address`, `txid` | **ACCEPT** |
| 5 — Crypto and Blockchain | **Blockchair API** | `address`, `txid` | **ACCEPT** |
| 5 — Crypto and Blockchain | **Etherscan API V2** | `EVM address`, `txid` | **ACCEPT** |
| 5 — Crypto and Blockchain | **crypttrace** | `wallet address` | **ACCEPT** |
| 5 — Crypto and Blockchain | **Bitquery** | `address` | **REJECT** |
| 5 — Crypto and Blockchain | **BlockCypher** | `address`, `txid` | **ACCEPT** |
| 5 — Crypto and Blockchain | **Chainabuse** | `address`, `URL` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Companies House API** | `company name`, `company number`, `officer name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **German Handelsregister** | `company name`, `register number` | **REJECT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Data INPI RNE** | `company name`, `siren/siret` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **KVK Business Register API** | `company name`, `kvk number` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **ASIC Registry APIs** | `company name`, `acn/abn` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **NZBN API** | `company name`, `nzbn` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **CIPC / BizPortal** | `company name`, `enterprise number` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Judyrecords API** | `person name`, `case number` | **DEFER** |
| 6 — Corporate/Legal/Financial/Sanctions | **Trellis API** | `person name`, `case number` | **REJECT** |
| 6 — Corporate/Legal/Financial/Sanctions | **PACER Case Locator API** | `person name`, `case number` | **DEFER** |
| 6 — Corporate/Legal/Financial/Sanctions | **FINRA BrokerCheck** | `person name`, `crd number` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **FDIC BankFind Suite API** | `bank name`, `institution id` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Federal Reserve Enforcement Actions** | `person name`, `bank name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **OCC Enforcement Actions Search** | `bank name`, `person name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **UK Sanctions List** | `person name`, `entity name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Swiss SECO Sanctions List** | `person name`, `company name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **EU Consolidated Sanctions** | `person name`, `organisation name` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **USAspending API** | `company name`, `recipient id` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **SAM.gov APIs** | `company name`, `uei`, `cage code` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **Lobbying Disclosure Act API** | `lobbyist name`, `organisation` | **ACCEPT** |
| 6 — Corporate/Legal/Financial/Sanctions | **FollowTheMoney API** | `donor name`, `candidate` | **ACCEPT** |
| 7 — Government and Public Records | **MuckRock API** | `agency`, `person name` | **DEFER** |
| 7 — Government and Public Records | **FOIA.gov API** | `agency`, `office` | **ACCEPT** |
| 7 — Government and Public Records | **Regrid Parcel API** | `owner name`, `address`, `parcel number` | **REJECT** |
| 7 — Government and Public Records | **ReportAll USA Parcel API** | `owner name`, `address`, `county` | **REJECT** |
| 7 — Government and Public Records | **NHTSA vPIC** | `vin` | **ACCEPT** |
| 7 — Government and Public Records | **Federal BOP Inmate Locator** | `name`, `register number` | **ACCEPT** |
| 7 — Government and Public Records | **ICE Online Detainee Locator** | `name`, `a-number` | **REJECT** |
| 7 — Government and Public Records | **Florida Voter Extract** | `name`, `county` | **REJECT** |
| 7 — Government and Public Records | **NYC Open Data API** | `person name`, `date`, `location` | **ACCEPT** |
| 7 — Government and Public Records | **County Assessor / Recorder Datasets** | `jurisdiction-specific` | **REJECT** |
| 7 — Government and Public Records | **State DOC Inmate Portals** | `state-specific` | **REJECT** |
| 7 — Government and Public Records | **NSOPW** | `person name`, `location` | **REJECT** |
| 8 — Transport | **OpenSky Network API** | `icao24`, `time`, `bbox` | **ACCEPT** |
| 8 — Transport | **ADS-B Exchange API** | `icao hex`, `registration`, `callsign` | **REJECT** |
| 8 — Transport | **Aviation Edge API** | `flight number`, `registration` | **REJECT** |
| 8 — Transport | **FlightAware AeroAPI** | `flight identifier`, `airport` | **REJECT** |
| 8 — Transport | **FAA Aircraft Registration** | `tail number` | **ACCEPT** |
| 8 — Transport | **IMO GISIS** | `imo number`, `vessel name` | **REJECT** |
| 8 — Transport | **VesselFinder API** | `vessel name`, `mmsi`, `imo` | **REJECT** |
| 8 — Transport | **Datalastic API** | `vessel name`, `mmsi`, `imo` | **REJECT** |
| 8 — Transport | **BarentsWatch AIS API** | `mmsi`, `time`, `coordinates` | **ACCEPT** |
| 8 — Transport | **MarineTraffic AIS API** | `vessel identifier`, `mmsi` | **REJECT** |
| 8 — Transport | **Paris MoU / THETIS** | `vessel name` | **REJECT** |
| 8 — Transport | **Tokyo MoU PSC** | `vessel name` | **REJECT** |
| 8 — Transport | **Network Rail Open Data** | `train/service identifier` | **ACCEPT** |
| 8 — Transport | **National Rail Data** | `station`, `service` | **ACCEPT** |
| 8 — Transport | **Deutsche Bahn Timetables API** | `station`, `train`, `date` | **ACCEPT** |
| 8 — Transport | **OpenRailwayMap API** | `station/facility`, `uic` | **ACCEPT** |
| 8 — Transport | **ERATV** | `vehicle type` | **ACCEPT** |
| 8 — Transport | **Planespotters API** | `aircraft registration`, `hex` | **ACCEPT** |
| 8 — Transport | **AIS Hub** | `vessel identifier`, `mmsi` | **REJECT** |
| 8 — Transport | **ICAO 24-bit Database** | `icao hex` | **REJECT** |
| 9 — Patents and Trademarks | **PatentsView** | `patent number`, `inventor`, `assignee` | **ACCEPT** |
| 9 — Patents and Trademarks | **USPTO Open Data Portal** | `patent`, `trademark` | **ACCEPT** |
| 9 — Patents and Trademarks | **USPTO Patent Assignment Search** | `patent number`, `assignor`, `assignee` | **ACCEPT** |
| 9 — Patents and Trademarks | **USPTO TSDR** | `trademark serial/reg number` | **ACCEPT** |
| 9 — Patents and Trademarks | **EPO OPS** | `publication/app number`, `applicant` | **ACCEPT** |
| 9 — Patents and Trademarks | **WIPO PATENTSCOPE** | `PCT application number` | **REJECT** |
| 9 — Patents and Trademarks | **Lens API** | `inventor`, `applicant`, `identifier` | **REJECT** |
| 9 — Patents and Trademarks | **Google Patents Public Datasets** | `patent number`, `inventor`, `assignee` | **ACCEPT** |
| 9 — Patents and Trademarks | **JPO APIs** | `applicant`, `application number` | **DEFER** |
| 9 — Patents and Trademarks | **WIPO Global Brand Database** | `trademark name`, `owner` | **REJECT** |
| 9 — Patents and Trademarks | **EUIPO eSearch plus** | `mark/name`, `owner` | **ACCEPT** |
| 9 — Patents and Trademarks | **TMview** | `mark name`, `owner` | **REJECT** |
| 9 — Patents and Trademarks | **DesignView** | `design identifier`, `owner` | **REJECT** |
| 9 — Patents and Trademarks | **IP India** | `applicant`, `patent number` | **REJECT** |
| 9 — Patents and Trademarks | **CNIPA** | `applicant`, `application number` | **REJECT** |
| 9 — Patents and Trademarks | **UK IPO API programme** | `patent number` | **REJECT** |
| 10 — Search Engines | **SearXNG** | `keyword`, `domain`, `URL` | **ACCEPT** |
| 10 — Search Engines | **Mojeek API** | `keyword`, `domain`, `URL` | **REJECT** |
| 10 — Search Engines | **Marginalia Search API** | `keyword`, `URL` | **ACCEPT** |
| 10 — Search Engines | **Brave Search API** | `keyword`, `domain`, `URL` | **REJECT** |
| 10 — Search Engines | **Google Custom Search JSON API** | `keyword` | **ACCEPT** |
| 10 — Search Engines | **Kagi Search API** | `keyword` | **REJECT** |
| 10 — Search Engines | **Common Crawl Index API** | `URL`, `domain` | **ACCEPT** |
| 10 — Search Engines | **Whoogle** | `keyword`, `URL` | **REJECT** |
| 11 — Academic | **OpenAlex API** | `author`, `institution`, `DOI` | **ACCEPT** |
| 11 — Academic | **Crossref REST API** | `title`, `author`, `DOI` | **ACCEPT** |
| 11 — Academic | **Semantic Scholar** | `author`, `paper title`, `DOI` | **ACCEPT** |
| 11 — Academic | **arXiv API** | `author`, `title`, `category`, `id` | **ACCEPT** |
| 11 — Academic | **CORE API** | `author`, `title`, `DOI` | **ACCEPT** |
| 11 — Academic | **Unpaywall API** | `DOI`, `email` | **ACCEPT** |
| 11 — Academic | **BASE OAI** | `title`, `author` | **DEFER** |
| 11 — Academic | **Dimensions Analytics API** | `author`, `publication` | **REJECT** |
| 11 — Academic | **OpenAIRE Graph API** | `title`, `author`, `DOI` | **ACCEPT** |
| 12 — Paste and Code | **Pastebin Developers API** | `text`, `paste ID` | **REJECT** |
| 12 — Paste and Code | **GitLab Search API** | `keyword`, `code snippet` | **ACCEPT** |
| 12 — Paste and Code | **Sourcegraph API** | `keyword`, `code snippet` | **REJECT** |
| 12 — Paste and Code | **Debian Code Search API** | `keyword`, `package` | **ACCEPT** |
| 12 — Paste and Code | **PublicWWW API** | `keyword`, `source-code snippet` | **ACCEPT** |
| 12 — Paste and Code | **NerdyData API** | `code snippet`, `technology` | **REJECT** |
| 13 — Email Authentication | **MXToolbox Lookup API** | `domain`, `IP`, `DKIM selector` | **REJECT** |
| 13 — Email Authentication | **dmarcian REST API** | `domain`, `DKIM selector` | **REJECT** |
| 13 — Email Authentication | **EasyDMARC Public API** | `domain`, `SPF`, `DKIM selector` | **REJECT** |
| 13 — Email Authentication | **checkdmarc** | `domain`, `DNS records` | **ACCEPT** |
| 13 — Email Authentication | **scan.mx API** | `domain`, `DNS records` | **ACCEPT** |
| 13 — Email Authentication | **MXToolbox Header Analyzer** | `raw email header` | **REJECT** |
| 13 — Email Authentication | **Google Admin Messageheader** | `raw email header` | **REJECT** |
| 14 — SSL/TLS | **Qualys SSL Labs API** | `domain`, `hostname`, `IP` | **ACCEPT** |
| 14 — SSL/TLS | **Hardenize Organization API** | `domain`, `hostname`, `cert hash` | **REJECT** |
| 14 — SSL/TLS | **testssl.sh** | `domain`, `hostname`, `IP`, `port` | **ACCEPT** |
| 14 — SSL/TLS | **CipherScan** | `domain`, `hostname`, `IP`, `port` | **ACCEPT** |
| 14 — SSL/TLS | **CertGraph** | `domain`, `hostname`, `IP` | **ACCEPT** |
| 14 — SSL/TLS | **sslscan** | `domain`, `hostname`, `IP`, `port` | **ACCEPT** |
| 14 — SSL/TLS | **tlsx** | `domain`, `hostname`, `IP`, `CIDR`, `ASN` | **ACCEPT** |
| 15 — IP Intelligence | **IPinfo API** | `ip`, `asn` | **ACCEPT** |
| 15 — IP Intelligence | **IP-API** | `ip`, `domain` | **ACCEPT** |
| 15 — IP Intelligence | **ipapi.co** | `ip` | **ACCEPT** |
| 15 — IP Intelligence | **IPGeolocation.io** | `ip`, `domain`, `user-agent` | **ACCEPT** |
| 15 — IP Intelligence | **AbuseIPDB API v2** | `ip`, `cidr` | **ACCEPT** |
| 15 — IP Intelligence | **GreyNoise Community API** | `ip` | **ACCEPT** |
| 15 — IP Intelligence | **VirusTotal API v3** | `ip`, `domain`, `url`, `hash` | **ACCEPT** |
| 15 — IP Intelligence | **CIRCL Passive DNS** | `ip`, `hostname`, `domain` | **DEFER** |
| 15 — IP Intelligence | **CIRCL Passive SSL** | `ip`, `cidr`, `cert fingerprint` | **DEFER** |
| 15 — IP Intelligence | **URLhaus Community API** | `url`, `domain`, `ip` | **ACCEPT** |
| 15 — IP Intelligence | **ThreatFox Community API** | `ip`, `domain`, `url`, `hash` | **ACCEPT** |
| 15 — IP Intelligence | **MalwareBazaar Community API** | `hash` (`md5`, `sha1`, `sha256`) | **ACCEPT** |
| 15 — IP Intelligence | **PhishTank API** | `url` | **ACCEPT** |
| 15 — IP Intelligence | **Censys Platform API** | `ip`, `domain`, `hostname`, `cert` | **REJECT** |
| 15 — IP Intelligence | **Netlas API** | `ip`, `cidr`, `domain`, `asn` | **ACCEPT** |
| 15 — IP Intelligence | **FullHunt API** | `domain`, `hostname`, `ip` | **ACCEPT** |
| 15 — IP Intelligence | **BinaryEdge Host Search API** | `ip`, `cidr`, `asn` | **REJECT** |
| 15 — IP Intelligence | **ZoomEye API** | `ip`, `domain`, `hostname` | **REJECT** |
| 15 — IP Intelligence | **HackerTarget API** | `ip`, `domain`, `cidr`, `asn` | **ACCEPT** |
| 15 — IP Intelligence | **ViewDNS.info Reverse IP API** | `ip`, `domain` | **REJECT** |
| 15 — IP Intelligence | **ipinfo.app ASN Lookup API** | `asn`, `ip` | **ACCEPT** |

## Handoff

Use only rows marked ACCEPT as the candidate pool for the batching plan. Keep each candidate's category, input types, auth/key requirements, terms, and rate-limit evidence attached to its planned source-registry entry. Where this transcript does not state a rate limit explicitly, mark it unknown and verify the upstream limit before the first implementation request.

This source review is not an adapter implementation or a live investigation. Do not upgrade any Aletheia adapter to verified-live from these candidate verdicts.
