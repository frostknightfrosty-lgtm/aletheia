# Source Completeness — Owner Directive Tracker (Phase 17)

> **Owner directive (2026-10-18).** Everything accepted in the 111-candidate
> verification sweep ([`VERIFICATION_COMPLETE.md`](VERIFICATION_COMPLETE.md)) and
> every source permitted by the Florida project policy
> ([`DIRECTIVE_AMENDMENT_FLORIDA.md`](DIRECTIVE_AMENDMENT_FLORIDA.md)) but not
> yet integrated is to be **fully integrated, wired, and working**. Nothing
> accepted or permitted stays backlogged, disabled, or dropped while a free,
> open path exists.
>
> Unchanged constraints: nothing paid (Gate 3); the Tier 5 floor; each source
> keeps its own scoped source / license / scope / implementation review before
> code; free-key registrations and provider permissions are owner actions;
> evidence is never fabricated (Gate 5) — an item blocked by vendor facts is
> recorded with evidence and re-checked, never faked.

Build sequencing: Phase 17 items **P17.11–P17.12** in
[`PIVOT_CASCADE.md`](PIVOT_CASCADE.md). This file is the status inventory.

## Completion standard — what "working" means here

1. Scoped review recorded (license, terms, interface, permitted invocation,
   rate limit, tier, response-field screening).
2. Adapter implemented: Docker-isolated, pinned upstream, parser, fixture,
   capture case, manifest entry (`legal_tier`, `enabled_by_default`,
   `batch_grouping`, `requires_key`).
3. CI-verified `verified-fixture` with evidence lines copied from the run
   artifact (Gate 5); parser preflight and capture counts updated.
4. Free-key / registration prerequisites obtained (owner action) or the source
   runs keyless; a missing key is a recorded skip with reason — never a silent
   absence.
5. Executed in an authorized live sweep where gates permit (Gates 2/3/6);
   per-source live evidence recorded.

## A. The 111 accepted candidates — remaining gaps

Already implemented and wired: **83 of 111** (the 57 CI-verified adapters for
accepted sources; the tree also has five P17.13 horizon adapters, for 62
registered total; some are key-gated — their skip reasons are recorded).
**28 of 111 remain.** Of these, two are
externally blocked (FollowTheMoney, GeoLocator),
several have owner-action prerequisites, and a few carry factual re-checks that
may resolve to a recorded blocker if the free path no longer exists. No status
below may be upgraded except from copied artifact lines.

| # | Item | Cat | State today | Path to "working" | Gate / owner action |
|---|------|----:|-------------|-------------------|---------------------|
| 1 | OWASP SocialOSINTLM | 1 | Disabled sub-source (`social_username`): external platform + LLM credentials | Re-review: free platform keys; free-tier or local LLM path; document what the LLM adds | Owner: platform dev keys |
| 2 | Zehef | 1 | **Wired (CI-verified)**: standalone email-input adapter running the 17 pinned upstream account modules (Zehef 2.2.1, commit `5b0c120efe846eae944dfea9410f925ca3036103`; paste-dump, HudsonRock and email-gen modules never invoked) — run `39171286556`, 1046 passed. See `docker/zehef/RATE_LIMITS.md` | Re-review: email→registered-accounts CLI; wrap in container if scoped | — |
| 3 | scrawler | 1 | Dropped: Windows-only .NET GUI; re-checked 2026-10-18 — upstream FAQ: no CLI will be added; site retrieval needs user cookies/OAuth. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Recorded as interface blocker 2026-10-18; re-open only on a vendor interface change | — |
| 4 | tiktok-hashtag-analysis | 1 | **Wired (CI-verified)**: standalone hashtag-input adapter (`SeedType.HASHTAG`) running the pinned Bellingcat library (commit `2a4af674efc4af7c7d592053ec3f475555f37694`; headless-only direct `_fetch_hashtag_data(..., headed=False)` call path, dependency stealth patching neutralized as a no-op, bot-detection responses recorded as `blocked`) — run `39174382751`, 1058 passed. See `docker/tiktok_hashtag/RATE_LIMITS.md` | Bellingcat PyPI library; re-review and implement (hashtag input) | — |
| 5 | OnionSearch | 2 | Not built; `darkweb_search` deferred (Gate 6) | Build in `darkweb_search` behind container-level Tor; per-engine notes (Ahmia/Torch/Candle; ToS risk recorded) | Tor setup |
| 6 | TorBot | 2 | Not built; Gate 6 | Build; crawler semantics (titles, links, emails) documented | Tor setup |
| 7 | Piano (darknet-crawler) | 2 | Not built; Gate 6 | Build; published single-engine search invocation; PyPI pin | Tor setup |
| 8 | Intelligence X | 2 | Not built; Gate 6 | Build with registered `x-key` (free tier ~50 selector searches/day) | Owner: register free key |
| 9 | BreachDirectory | 3 | Wired as documented skip (`leak_checkers`) | Implement live call path (RapidAPI); skip without key | Owner: free RapidAPI key |
| 10 | Leak-Lookup | 3 | Wired as documented skip (`leak_checkers`) | Implement live call path (`/api/search`, breach names only) | Owner: free registration key |
| 11 | Bron Vault | 3 | **Wired (CI-verified)**: loopback-only sub-source of `leak_checkers` for the operator's own self-hosted instance (contract pinned to release v1.4.0 commit `6bfdcc0196ac90ed38a35a1099697497680c1666`; non-loopback URLs refused before any socket; off-host redirects refused; proxies bypassed; skips unless `BRON_VAULT_URL`/`BRON_VAULT_API_KEY` set) — run `39168364470`, 1034 passed. See `docker/leak_checkers/RATE_LIMITS.md` | Build offline local-log parser adapter (no egress) | — |
| 12 | VENOM | 3 | **Wired (CI-verified)**: standalone one-off adapter over the pinned checkout (commit `6fa3a483abc9cb0a1d96567e33b2919be59522c6`; 29 upstream classes / 30 driver bindings — keyed services, scraping, and TLS-relaxation paths excluded with recorded reasons; honest-agent and forced-TLS deviations) — run `39196608448`, 1073 passed. See `docker/venom/RATE_LIMITS.md` | Build one-off; review and constrain its 25+-service request set | — |
| 13 | PicImageSearch | 4 | **Wired (CI-verified)**: standalone image-input adapter over the pinned upstream (commit `784713e546273a09aae4b247a8b6f798825efafa`; self-reported 3.12.11; MIT), running five keyless engines (IQDB, 3D IQDB, Ascii2D colour search, TraceMoe, AnimeTrace) plus the official SauceNAO API when `SAUCENAO_API_KEY` is set; consumer-web scrapers, Copyseeker, Lenso, TinEye and EHentai are never imported — run `39404418732`, 1089 passed. Fixture-only: no authorized live image target, so no live requests. See `docker/picimagesearch/RATE_LIMITS.md` | — |
| 14 | tracelines | 4 | **Wired (CI-verified)**: standalone point-input adapter over the pinned upstream (commit `99257f0519b30ce7d890db25252f6cf440fa102e`; tag v0.2.0; AGPL-3.0-or-later, operated unmodified in its own image), running only the documented Mapillary (free `MAPILLARY_TOKEN`; recorded skip without it) and keyless KartaView providers — the Google/streetlevel provider is structurally excluded (never installed; driver refuses if importable); one point seed with a ≤300 m bbox; summarized segments only with CC-BY-SA 4.0 attribution; no retries or disk cache — run `39416003189`, 1100 passed. Fixture-only: no authorized point seed, so no live requests. See `docker/tracelines/RATE_LIMITS.md` | — |
| 15 | ShadowFinder Web | 4 | **Wired (CI-verified)**: standalone offline adapter over the pinned Bellingcat library (commit `215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8`; tag v0.7.1; MIT), new `SeedType.SHADOW_OBSERVATION` for one object height, shadow length and UTC datetime; models the observation over the shipped 0.5° solar grid and returns ranked 1° possibility bins (bbox, centroid, best cell, relative difference, cell count) with bounded grid sampling and no coordinate or measurement transmitted — run `39448325747`, 1112 passed. Not a confirmed location; see `docker/shadowfinder/RATE_LIMITS.md` | — |
| 16 | pybdshadow | 4 | **Wired (CI-verified)**: standalone offline building-shadow adapter over the pinned pybdshadow 0.3.5 (commit `e2665ee7a6527b9fb0d581bbf7d6dc2914015b02`; BSD-3-Clause); a local file-seed JSON supplies 1–200 footprint polygons, heights and one UTC datetime; per-building shadow summaries (bbox, centroid, geodesic area, polygon/vertex counts) are computed under `--network none` — run `39457146650`, 1122 passed. Not a confirmed location; see `docker/pybdshadow/RATE_LIMITS.md` | — |
| 17 | youtube-geofind | 4 | Not built (one-off) | Build with YouTube Data API free quota | Owner: YT key |
| 18 | GeoLocator | 4 | **Blocked (upstream withdrawal)**: the MIT demo app depends on the GeoEstimation pre-trained ResNet; the official `TIBHannover/GeoEstimation` repository removed all source code and model weights, retains the repository for documentation only, and explicitly refrains from further public release (README "Important Notice", re-checked 2026-10-20); the checkpoint and hparams URLs used by the app return HTTP 404. The retained fork is not used because it would contradict the authors' withdrawal. See `docs/PHASE17_RECHECKS.md` #18 | — |
| 19 | Betaface | 4 | Not built (one-off) | Build with free evaluation tier (≤500 images/day); corroboration-only role; never sole basis | Owner: free key + secret |
| 20 | crypttrace | 5 | **Wired (CI-verified)**: standalone Bitcoin-only fund-flow adapter over the pinned crypttrace 0.22.0 library (MIT, commit `cf60a88b8be43581186965d160114fdaf3022c62`); the seed address is traced through mempool.space at depth 2 / branching 3 and the report JSON is reduced to bounded run, entity and counterparty records; labels are upstream leads, not attribution. Run `39466252253`, 1132 passed; no live target, fixture-verified. See `docker/crypttrace/RATE_LIMITS.md` | — |
| 21 | FollowTheMoney | 6 | Not built; **Gate 7 documented exclusion** | **Externally blocked**: no published request contract; parent OpenSecrets discontinued public API 2025-04-15; commercial route only. Re-open only on vendor change | — |
| 22 | OpenSky Network API | 8 | Not built; `transport_movement` deferred (Gate 6) | Build; free key (~4,000 req/day); written integration permission | Owner: register + written permission |
| 23 | BarentsWatch AIS | 8 | Not built; Gate 6 | Build; free OAuth 2.0 client credentials | Owner: register |
| 24 | Network Rail Open Data | 8 | Not built; Gate 6 | Build; free self-service key (REST/STOMP) | Owner: register |
| 25 | National Rail Data (Darwin) | 8 | Not built; Gate 6 | Build; free developer token | Owner: register |
| 26 | Deutsche Bahn Timetables | 8 | Not built; Gate 6 | Build; free client-id + secret | Owner: register |
| 27 | ERATV | 8 | Documented non-querying drop (`transport_asset_registry`); re-checked 2026-10-18 — no public SPARQL/RDF endpoint (host NXDOMAIN; browser-only app). See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Re-review public SPARQL/RDF endpoint; build query path or record live-probe evidence | — |
| 28 | PatentsView | 9 | Dropped: API host no longer resolves; re-checked 2026-10-18 — legacy host dead (NXDOMAIN), successor behind a USPTO portal account. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Re-check official host; build if live; else record evidence | Owner: USPTO Open Data Portal key |
| 29 | Google Patents Public Datasets | 9 | Dropped: GCP service account + client library; re-checked 2026-10-18 — BigQuery sandbox needs no billing account; build queued. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Re-review BigQuery free-tier path (no-billing route); build or record | Owner: Google sandbox token + project |
| 30 | EUIPO eSearch plus | 9 | Dropped: account + sandbox/production approval | Build via free developer account once approved | Owner: register EUIPO dev account |
| 31 | SearXNG | 10 | **Wired (CI-verified)**: third `search_engines` sub-source — a loopback-only instance operated inside `aletheia/search-engines:v1` (upstream pinned by commit `1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4`; engines duckduckgo/brave/wikipedia; JSON enabled in generated settings) — run `39166656036`, 1021 passed. See `docker/search_engines/RATE_LIMITS.md` | Build as a self-hosted container instance (JSON endpoint enabled) — free/open-source | — |
| 32 | Google Custom Search JSON API | 10 | Dropped: closed to new customers; sunset 2027-01-01; re-checked 2026-10-18 — notice stands; Marginalia + Common Crawl (integrated) carry the class. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Re-check access at review; if unavailable, record evidence (Marginalia + Common Crawl carry the class) | — |
| 33 | Unpaywall | 11 | **Wired (CI-verified)**: DOI-keyed live path (`GET /v2/:doi` with `UNPAYWALL_EMAIL`; name inputs keep the documented skip) — run `39160798771`, 1009 passed. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Implement the live DOI-keyed endpoint (only live route) | Owner: `UNPAYWALL_EMAIL` config (no registration) |
| 34 | GitLab Search API | 12 | Dropped: every call requires authentication (probe 401) | Implement with a free GitLab account token; skip without key | Owner: free token |
| 35 | PublicWWW | 12 | Dropped: vendor docs require a paid plan; re-checked 2026-10-18 — no free tier surfaced. See [`PHASE17_RECHECKS.md`](PHASE17_RECHECKS.md) | Re-check free tier at review; if paid-only, stays out under nothing-paid with evidence | — |
| 36 | CipherScan | 14 | **Wired (CI-verified)**: sixth `ssl_tls` sub-source — pinned by commit `30bd23938853d68b51c2ebe4bcc922cc3113c5e2` (project has no releases/tags; tolerance-test deps tlslite-ng v0.8.2 + python-ecdsa 0.19.2 pinned as well) — run `39167510546`, 1030 passed. See `docker/ssl_tls/RATE_LIMITS.md` | Re-review: pin a specific commit SHA as the verifiable artifact; build if pinnable | — |

## B. Policy-permitted, not-yet-integrated sources

Allowed by the Florida policy ([`DIRECTIVE_AMENDMENT_FLORIDA.md`](DIRECTIVE_AMENDMENT_FLORIDA.md))
or listed as review-gated expansions (`PIVOT_CASCADE.md` §10.1). Each gets its
scoped review first, then implementation.

| # | Source | Path to "working" | Safeguard notes |
|---|--------|-------------------|-----------------|
| 1 | LeakCheck (free OSINT-Hub path) | Build; review current API terms and scope | Breach indicators only as scoped; found material never used |
| 2 | LeakRadar | Build stealer-log checker | Structural safeguard; prefer signal/existence fields; credentials never used |
| 3 | OsintCat | Build aggregator adapter | May return tokens/passwords — structural safeguard; no credential use |
| 4 | OathNet | Build (breach + stealer + Discord data) | Structural safeguard; scope and response-field screening |
| 5 | Blackbird | Resolve license fact at review, then build username enumeration | No declared upstream license today — resolve before bundling |
| 6 | Lullar | Re-review for a bounded implementation; else record interface blocker with evidence | No documented machine-readable interface today |
| 7 | Hudson Rock | Build username endpoint | Structural safeguard before any credential-field parsing; signal fields preferred; found credentials never used |
| 8 | GHunt | Build; operator's own Google account only, explicit authorization | Read-only output; authenticated-workflow exception |
| 9 | People-search free tiers (TruePeopleSearch, Whitepages free, PeekYou) | Build free paths; politeness limits; firewall | Paid-only products rejected; coverage limits recorded |
| 10 | Face-search free paths | Build free-path services only (e.g. Betaface eval tier) | Corroboration only, never sole basis; paid products (PimEyes, FaceCheck.ID, Search4Faces, Lenso.ai programmatic) stay out under nothing-paid |
| 11 | Paste indexes (psbdmp-class, LeakCheck OSINT-Hub) | Build | Flag-only storage: existence, date, source name; never dump contents beyond evidence hashes |
| 12 | Reverse-image-search automation | Built as the standalone `picimagesearch` adapter (#13 in §A above): free engines only (IQDB, 3D IQDB, Ascii2D colour search, TraceMoe, AnimeTrace; optional SauceNAO) | Per-engine terms review; local pHash + archived captures remain the fallback |
| 13 | Dark-web engines (Ahmia, Torch, OnionLand, DarkSearch) | Wire through the darkweb_search composite / OnionSearch-class tooling | Ahmia and similar prohibit scraping — recorded ToS risk under the Florida posture; OnionLand/DarkSearch interface review; Tor container setup |
| 14 | Bulk/paste data processing | Policy capability; no separate adapter | Retention and flag rules apply |

Note: email-existence checks (holehe-class) listed in `PIVOT_CASCADE.md` §10.1
are **already integrated** (`holehe`, `h8mail`) — verify coverage, do not
duplicate. LinkedIn-enumeration-class additions (InSpy-class) may only be
integrated under the adapter safety rule (read-only fields: name, username,
email, company, source_url).

## C. Owner actions — free registrations and provider permissions

The engine's next-actions checklist enumerates these per run; this is the
grouped master list. All are free-tier registrations or permissions; no paid
defaults.

- **Breach / leak / exposure:** RapidAPI account (BreachDirectory free tier),
  Leak-Lookup registration, LeakCheck, Hudson Rock, Intelligence X (`x-key`),
  LeakIX, GrayhatWarfare, abuse.ch portal (URLhaus / ThreatFox / MalwareBazaar).
- **IP intel:** IPinfo, IPGeolocation.io, AbuseIPDB, GreyNoise, VirusTotal,
  Netlas, FullHunt, (optional) PhishTank `app_key`.
- **Corporate / government:** Companies House, KVK, NZBN, ASIC, CIPC, EUIPO dev
  account (approval gate), `api.data.gov` (FOIA, SAM.gov).
- **Crypto:** Etherscan, Chainabuse.
- **Code / search / academic:** GitLab token, Debian Salsa (DCS key),
  Marginalia email key, Semantic Scholar, CORE, EPO OPS, USPTO Open Data
  Portal key (PatentsView migration — free account with identity fields).
- **Social / media:** Reddit, YouTube Data API, GitHub token, Mapillary,
  Copernicus Data Space, Betaface.
- **Transport (with Gate 6 items):** OpenSky (registration + written
  integration permission), BarentsWatch, Network Rail, National Rail,
  Deutsche Bahn.

Configuration secrets (no registration): `UNPAYWALL_EMAIL` (Unpaywall
requires a contact email on its documented DOI endpoint) and
`GOOGLE_BIGQUERY_ACCESS_TOKEN` + `GOOGLE_CLOUD_PROJECT` (BigQuery sandbox
queries over the public patents datasets).
- Already-wired keyed adapters (Shodan, OpenCorporates, HIBP, etc.) keep their
  recorded key states; HIBP direct email lookups remain out under nothing-paid.

## D. Recorded blockers and unchanged exclusions

- **FollowTheMoney** — Gate 7 documented exclusion (no published request
  contract; OpenSecrets API discontinued 2025-04-15; commercial only). Re-open
  only if the vendor publishes a contract or a free route.
- **Re-check items that may resolve to blockers:** PatentsView, Google Custom
  Search, PublicWWW, crypttrace, Google Patents BigQuery. If the free
  path no longer exists, record the evidence and the resulting exclusion — do
  not fabricate a path.
- **The 7 deferred candidates** (Judyrecords, PACER Case Locator, MuckRock,
  JPO APIs, BASE OAI, CIRCL Passive DNS, CIRCL Passive SSL) are not part of the
  111 accepted set; they remain deferred unless the owner extends the directive.
- **Still excluded (unchanged):** ONYPHE (own-systems Free View mismatch);
  Mr.Holmes; IVRE; urlscan; ThreatCluster; Social Analyzer; DarkNyx;
  osint-darkweb-pkg; removed integrations (Twilio Lookup, Censys, Google Cloud
  Vision); Tier-5-risk candidates (Discord History Tracker, ICE Detainee
  Locator, NSOPW, IP India).
- **Paid-only products stay out** under the nothing-paid rule (DeHashed,
  Snusbase, HIBP stealer-log enterprise endpoints, PimEyes, FaceCheck.ID,
  Search4Faces, Lenso.ai programmatic access, and similar).

## E. Update rule

- Statuses move only from copied artifact lines; this directive never upgrades
  a source by itself.
- Docs/state commits stay separate from code commits; each build step lands
  with its CI verification (Gate 5 evidence).
