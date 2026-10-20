# Phase 17 Wave-A live re-checks (2026-10-18)

Inventory rows in [`SOURCE_COMPLETENESS.md`](SOURCE_COMPLETENESS.md) §A whose
state depends on vendor facts carry a "re-check" path. This file is the dated
evidence record of those live re-checks. Probes were run from the campaign
workstation on **2026-10-18**; DNS answers are the tool-reported
`Resolve-DnsName` records and HTTP results are the tool-observed outcomes.
Nothing here is inferred: an item that could not be verified stays recorded as
unverified, and re-opens only on a vendor change.

## #28 PatentsView — legacy API host is dead; successor needs a USPTO account

- `Resolve-DnsName search.patentsview.org` → **NO DNS RECORD** (the name does
  not exist; the apex `patentsview.org` still resolves to Cloudflare IPs).
- `GET https://search.patentsview.org/` → no HTTP response (transport error).
- rOpenSci tech note (2026-03-10,
  <https://ropensci.org/blog/2026/03/10/patentsview-breaking-release/>),
  verbatim:
  > the PatentsView API team had made breaking changes and obsoleted the
  > original API (all calls to the original endpoints return 410 Gone)

  > In late February they replaced their forum with a message saying the page
  > was temporarily unavailable. Further, they have also removed the link to
  > request an API key, so it's unclear whether they'd honor requests for API
  > keys using the link below. Nothing has been officially announced but the
  > long term viability of the API seems uncertain.
- USPTO transition guide (search-result snippet, `data.uspto.gov`):
  "API keys for accounts that did not complete these fields by October 8,
  2026, have been deactivated." — the successor route is the USPTO Open Data
  Portal behind an account with identity fields, not an anonymous key.
- **Outcome:** the recorded drop reason ("API host no longer resolves") is
  re-confirmed with fresh evidence. A successor route exists only behind a
  free USPTO portal account — owner action recorded. No endpoint contract is
  readable without that account, so no adapter code is written against a
  guessed host.

## #27 ERATV — no public SPARQL/RDF endpoint; browser-only registry

- `Resolve-DnsName data.era.europa.eu` → **SOA** (NXDOMAIN: the presumed
  Knowledge-Graph host does not exist in DNS).
- `GET https://data.era.europa.eu/` → no HTTP response (transport error).
- `GET https://eratv.era.europa.eu/` → the ERATV browser application loads
  (search and advanced-search forms, "View Registered Authorisations", Terms
  of Use); no API, SPARQL or RDF link is offered.
- **Outcome:** the blocker recorded in `transport_asset_registry.py` stands —
  the register is browser-hosted and no public SPARQL/RDF service is a
  verified ERATV data endpoint. Re-open on any ERA publication of a
  machine-readable endpoint.

## #29 Google Patents Public Datasets — no-billing route exists (sandbox)

- <https://cloud.google.com/bigquery/docs/sandbox> verbatim:
  > The BigQuery sandbox lets you experience BigQuery without providing a
  > credit card or creating a billing account for your project.
- **Outcome:** the nothing-paid route exists (BigQuery sandbox). Querying the
  public `patents-public-data` datasets still requires a Google-account access
  token, which is an owner-provided configuration value. The build (a
  `google_patents` sub-source over the documented BigQuery REST `jobs.query`
  endpoint, with a skip-without-token path) is queued in this P17.11 wave.

## #32 Google Custom Search JSON API — closed to new customers

- <https://developers.google.com/custom-search/v1/overview> verbatim (page
  "Last updated 2026-02-18 UTC"):
  > Note: The Custom Search JSON API is closed to new customers. Vertex AI
  > Search is a favorable alternative for searching up to 50 domains.
  > …Existing Custom Search JSON API customers have until January 1, 2027 to
  > transition to an alternative solution.

  > This API is not available for new customers.
- **Outcome:** unavailable for this project; stays out. The class is carried
  by integrated sub-sources: `search_engines` queries **marginalia** and the
  **common-crawl-index** (confirmed in
  `app/aletheia/adapters/search_engines.py`).

## #35 PublicWWW — no free tier surfaced; stays out under nothing-paid

- `GET https://publicwww.com/pricing.html` → the vendor serves a browser
  verification wall ("Checking your browser before continuing"); no free tier
  appears on the page; footer © 2005-2026.
- **Outcome:** the recorded reason ("vendor docs require a paid plan") is not
  contradicted and no free tier surfaced. Stays out with this evidence;
  re-open only on a vendor free-tier change.

## #33 Unpaywall — DOI-keyed endpoint live; email parameter enforced

- `GET https://api.unpaywall.org/v2/10.1038/nature12373?email=contact@example.com`
  → **HTTP 422** (the endpoint answers; the request with a placeholder contact
  address was refused).
- The official product page (<https://unpaywall.org/products/api>) served no
  readable content to the fetcher during this review, so no rate-limit number
  is quoted here; the adapter records "not readable at review" rather than a
  guessed number.
- **Outcome:** build the live DOI path in the `academic_search` runner
  (this P17.11 unit): DOI-shaped input → `GET /v2/{doi}` with the
  `UNPAYWALL_EMAIL` contact secret; every other input keeps the documented
  skip. The contact email is an owner-provided secret (no registration).

## #36 CipherScan — pinnable commit confirmed (2026-10-18)

- GitHub API (2026-10-18): the repository has **0 releases** and no tags, so a
  commit SHA is the only verifiable artifact — matching the inventory path.
- Repository facts: `mozilla/cipherscan`, license **MPL-2.0**, default branch
  `master`, not archived.
- Pinned commit: **`30bd23938853d68b51c2ebe4bcc922cc3113c5e2`** (2025-06-09,
  the current `master` tip). Its only change over its parent
  (`5866911b6207fb29491b6a625f62cea441961e5d`) is a one-line portability fix
  in `cscan.sh`: `python` → `python3`. The exact diff was reviewed here
  before pinning; nothing else is taken from that merge.
- **Outcome:** the build unit (a Dockerfile cloning the repository at that
  SHA, a capture case, and the wiring into `ssl_tls`) is queued behind the
  SearXNG unit; the SHA above is the artifact to verify against on rebuild.

## #3 scrawler — Windows-only GUI; upstream states no CLI (re-checked 2026-10-18)

- `FAQ.md` verbatim (<https://github.com/AAndyProgram/SCrawler/blob/main/FAQ.md>,
  section "Does this program have a GUI or CLI, and will a CLI be added in the
  future"):
  > This is a GUI program and **NO**, CLI will not be added
- `README.md` verbatim
  (<https://github.com/AAndyProgram/SCrawler/blob/main/README.md>):
  > I highly doubt you can run SCrawler on Linux or Mac. SCrawler is a program
  > that is heavily dependent on Windows.
- README requirements: "**Windows 10, 11** with NET Framework 4.6.1 or
  higher"; the FAQ's "What file executes the program" names **`SCrawler.exe`**
  — a .NET/vb.net desktop application, not a container-friendly binary.
- The FAQ's per-site retrieval paths are credential-bound, verbatim:
  > Reddit: add cookies and/or configure [OAuth]… **Reddit profiles can be
  > downloaded without credentials using cookies.**

  > **META** (**Instagram**, Threads, Facebook): you need **cookies** and fill
  > in **all fields**
- **Outcome:** no headless read-only subset exists to wrap. The upstream is an
  interactive Windows GUI with no CLI and no plan for one ("CLI will not be
  added"), and its site retrieval requires user cookies/OAuth. The row-3
  interface blocker is recorded; re-open only if upstream ships a non-GUI
  interface.

## #4 tiktok-hashtag-analysis — scoped review outcome (2026-10-18)

- License: MIT (upstream `LICENSE`, bellingcat/tiktok-hashtag-analysis). The
  checkout pins commit `2a4af674efc4af7c7d592053ec3f475555f37694` (main,
  2024-03-11; confirmed with `git ls-remote` on 2026-10-18).
- The recorded `social_profile` drop reason was two-fold: the upstream wrapper
  retries headed after any error, and the dependency (TikTokApi) hardcodes
  browser stealth patching to avoid bot detection. Both are resolved:
  - The headed retry is structural: the driver calls
    `tiktok_hashtag_analysis.base._fetch_hashtag_data` directly with
    `headed=False`; the wrapper that retries headed is never reachable and the
    driver contains no headed path at all.
  - The stealth patching is a policy line, not a workaround: TikTokApi 6.2.2
    calls `stealth_async(page)` unconditionally inside `create_sessions` (no
    off switch). `docs/LEGAL_MODEL.md` rejects evasion of platform controls,
    so the driver replaces `TikTokApi.tiktok.stealth_async` with a no-op
    before any session is created. The adapter makes plainly automated,
    headless requests and records TikTok's bot-detection response honestly
    (`EmptyResponseException` → recorded `blocked` status; no retry loop, no
    challenge handling, no cookies, no ms_tokens).
- No downloads (`yt_dlp` is never invoked), no plotting, no config files, no
  media; one hashtag per invocation, a bounded post sample.
- **Outcome:** build path cleared; the standalone hashtag-input adapter
  (`SeedType.HASHTAG`) is the next Wave A unit. Live success is expected to be
  limited by TikTok's bot detection; live coverage stays subject to the
  standing live-run policy (Gate 2) and is not claimed.

### Live-orchestration addendum (2026-10-18, post-verification)

- The standalone adapter is CI-verified (run `39174382751`, capture 67/67,
  including `phase17-tiktok-hashtag-health` and
  `phase17-tiktok-hashtag-selftest` under `--network none`).
- Egress reality for orchestrated live runs: the orchestrator passes
  `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` to adapter containers, but headless
  Chromium does not honor those environment variables (the session's API
  fetches execute inside the browser), and the pinned `_fetch_hashtag_data`
  call path passes no proxy option. On the orchestrator's `--internal`
  network a live run therefore **fails closed** (the browser simply has no
  egress) rather than bypassing the proxy; the Phase 15 policy still counts
  the adapter as wired (`network_required=True`). An explicit proxy-capable
  launch path is a recorded decision item, not claimed. Same record:
  `docker/tiktok_hashtag/RATE_LIMITS.md`. Not owner-gated.

## #12 VENOM — scoped review outcome (2026-10-19)

- License: MIT (upstream `LICENSE`, ghostport-sudo/VENOM). The project
  publishes no releases or tags; the checkout pins commit
  `6fa3a483abc9cb0a1d96567e33b2919be59522c6` (main, 2026-06-28, version 7.0).
- Reviewed and locked in `docker/venom/RATE_LIMITS.md`: 29 upstream classes /
  30 driver bindings across email, username, and domain seeds — 5 email /
  12 username / 13 domain modules, one query each. Excluded with recorded
  reasons: every keyed service (HIBP, BreachDirectory, LeakCheck, OSINTLeak,
  IntelX, Phonebook, Hunter, NumLookup), the borrowed-key Leak-Lookup module,
  the Dehashed scrape, the Holehe/Google login-form probes, the raw-socket
  SSL/RBL checks, the plain-HTTP ip-api path, the DuckDuckGo scrape, the AI
  agent, dorks/export/render, and the web UI.
- Two documented fail-closed deviations: the rotating browser user agents are
  replaced with the fixed honest `Aletheia/0.9.0 (venom)` agent on every
  module object, and upstream's hardcoded `ssl=False` is overridden by a
  session class that forces certificate verification.
- **Outcome:** built and CI-verified — run `39196608448` (parser preflight
  52/52; 1073 passed; capture 69/69, including `phase17-venom-health` and
  `phase17-venom-selftest` under `--network none`; selftest 7/7 checks). The
  dropped `phone` input type depends on a NumLookupAPI key and is recorded as
  an optional owner item; nothing else in VENOM's reviewed surface is
  owner-gated.

## #13 PicImageSearch — scoped review outcome (2026-10-20)

- License: MIT (upstream `LICENSE`, kitUIN/PicImageSearch). The last release
  tag (`v3.9.7`, 2023-12-12) predates the current network layer and engine
  set, so the checkout pins commit
  `784713e546273a09aae4b247a8b6f798825efafa` (main, 2026-10-10; self-reported
  version `3.12.11`).
- Reviewed and locked in `docker/picimagesearch/RATE_LIMITS.md`: five keyless
  engines — IQDB, 3D IQDB, Ascii2D colour search, TraceMoe, AnimeTrace — one
  request each, plus the official SauceNAO JSON API only when
  `SAUCENAO_API_KEY` is set (recorded skip otherwise). Excluded with recorded
  reasons: the consumer-web scrapers (Google, Google Lens, Yandex, Bing,
  Baidu), the token-refresh Copyseeker scraper, the Turnstile-blocked Lenso
  client, the TinEye web-app scrape, the adult-gallery EHentai engine, and the
  demos/tooling/composite methods.
- Two documented fail-closed deviations: the package's hardcoded browser user
  agent is replaced with the fixed honest `Aletheia/0.9.0 (picimagesearch)`
  agent (re-checked against each engine's client before every run), and TLS
  verification is never disabled.
- **Outcome:** built and CI-verified — run `39404418732` (parser preflight
  53/53; 1089 passed; capture 71/71, including
  `phase17-picimagesearch-health` and `phase17-picimagesearch-selftest` under
  `--network none`; the health reported five engine bindings with the honest
  UA and TLS verification, and the selftest ran 9/9 checks). Fixture-verified
  only: no authorized live image target exists, so no live requests were
  made. The optional SauceNAO key is recorded as an owner item.

## #14 tracelines — scoped review outcome (2026-10-20)

- License: AGPL-3.0-or-later (upstream `LICENSE`), version 0.2.0, pinned at
  commit `99257f0519b30ce7d890db25252f6cf440fa102e` (tag `v0.2.0`, released
  2026-07-14). Operated unmodified in its own image (the SearXNG copyleft
  precedent); the Aletheia driver is separate and the package is not patched.
- Reviewed and locked in `docker/tracelines/RATE_LIMITS.md`: documented
  providers only — Mapillary sequence vector tiles (free `MAPILLARY_TOKEN`;
  recorded skip without it) and keyless KartaView sequences. The Google
  provider is excluded structurally: the package is installed without
  `streetlevel`, the driver refuses to run if it becomes importable, and the
  image carries no Google credentials or endpoints. One point seed, a derived
  ≤300 m bbox, one to four Mapillary z14 tile requests and at most two
  KartaView sequence requests; no retries (`max_retries=1`), no disk cache, no
  pagination.
- Output is summarized in memory (segment length, point count, centroid,
  endpoints, capture date) with Mapillary/KartaView CC-BY-SA 4.0 attribution;
  no coverage geometry is written or redistributed. The query point and derived
  bbox are transmitted to both providers, so a live run needs an explicit Gate 2
  authorization; none exists, so the adapter is fixture-verified only.
- Fail-closed properties checked at start-up: honest fixed UA
  `Aletheia/0.9.0 (tracelines)`, static TLS scan of the pinned sources, pin file
  matches the commit, and provider construction succeeds without the excluded
  Google dependency.
- **Outcome:** built and CI-verified — run `39416003189` on commit `0ac22ed`
  (parser 54/54; 1100 passed; capture 73/73, including
  `phase17-tracelines-health` and `phase17-tracelines-selftest` under
  `--network none`, 10/10 selftest checks). The first attempt exposed a real
  image defect: Python 3.11 could not install `networkx==3.7`; the image now
  builds on Python 3.12.

## #15 ShadowFinder Web — scoped review outcome (2026-10-20)

- License: MIT (upstream `LICENSE`), version 0.7.1, pinned at commit
  `215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8` (tag `v0.7.1`, released
  2026-09-03). The package is operated unmodified in its own image; the
  Aletheia driver is separate and the package is not patched.
- Interface: the upstream CLI (`fire` + `quick_find`) only renders a PNG and
  regenerates the timezone grid on demand. The driver calls the library
  directly (`ShadowFinder` plus the shipped `timezone_grid.json`) and
  summarises the likelihood grid, so no plotting or file output is involved.
- Offline by construction: one `SHADOW_OBSERVATION` seed (object height,
  shadow length, UTC datetime, tolerance, bin size) is evaluated over the
  shipped 0.5° grid; no coordinate, measurement or query is transmitted, no
  request library is imported, and the capture runs under `--network none`.
  The model is a possibility band from solar geometry, not a probability or a
  confirmed location.
- Bounds reviewed and locked in `docker/shadowfinder/RATE_LIMITS.md`: tolerance
  0.10 (max 0.5), 1° summary bins (0.25–5°), top 20 regions (max 50), grid
  step 1 (max 4), dates 1900–2100, grid latitude −60..85° (polar regions
  excluded). Bins are grid-aligned boxes, not connected components; the
  centroid is the mean of matching cells; the grid is sampled coarsely for
  larger steps.
- No owner action is needed: the computation is local and fixture-verified;
  no Gate 2 live target exists or is required.
- **Outcome:** built and CI-verified — run `39448325747` on commit `5ddf240`
  (parser 55/55; 1112 passed; capture 75/75, including
  `phase17-shadowfinder-health` (`ok`) and
  `phase17-shadowfinder-selftest` (9/9 checks) under `--network none`). The
  unit's first run (`0eca2b4`) exposed a selftest bug: the check asserted
  `_parse_args` rejects a malformed observation, but `_parse_args` is syntactic
  and `main` rejects invalid observations via `_parse_observation`; the check
  now exercises that contract and a regression test pins it.

## #16 pybdshadow — scoped review outcome (2026-10-20)

- License: BSD-3-Clause (upstream `LICENSE`), version 0.3.5, pinned at commit
  `e2665ee7a6527b9fb0d581bbf7d6dc2914015b02` (2025-03-19). The package is
  installed unmodified in its own image; the Aletheia driver is separate.
- Interface: one local JSON document (`SeedType.FILE_PATH`) with a UTC
  datetime and a GeoJSON FeatureCollection of Polygon footprints carrying
  `height` and optional `building_id`. The driver builds a WGS84 GeoDataFrame
  and calls `pybdshadow.bdshadow_sunlight`, then summarises the returned
  shadow geometries.
- Offline by construction: no request library is called by the driver; the
  package's optional footprint-fetching helpers (`get_buildings`, which uses
  `requests`/`vt2geojson`) are never invoked, and every capture case runs under
  `--network none`. The image installs the package without its `keplergl`
  extra; import-time analysis/visualisation modules work with `transbigdata`
  installed.
- Bounds reviewed and locked in `docker/pybdshadow/RATE_LIMITS.md`: at most
  1,000,000 input bytes, 1–200 buildings, 4–1,000 vertices per exterior ring,
  heights 0.1–1,000 m, dates 1900–2100, WGS84 lon/lat checks, closed rings,
  no holes (the upstream routine uses the exterior ring), unique building ids.
  The sun position is computed at the centre of the footprint bounds; when the
  sun is below the horizon the driver returns `status: "no_sunlight"` with exit
  code 0.
- Output is per-building summary geometry (`bbox`, `centroid`,
  `shadow_area_m2`, `polygons`, `vertices`), not a confirmed location,
  probability, or redistributable footprint dataset.
- No owner action is needed: the input is owner-supplied and the computation is
  local; there is no Gate 2 live target for a building-shadow capability, and
  none is required.
- **Outcome:** built and CI-verified — run `39457146650` on commit `4505ae5`
  (parser 56/56; 1122 passed; capture 78/78, including
  `phase17-pybdshadow-health` (`ok`), `phase17-pybdshadow-selftest` (8/8
  checks) and the synthetic `phase17-pybdshadow-run` under `--network none`).
  The library was first validated locally against the exact pinned stack
  (geopandas 1.2.0, pandas 3.0.6, shapely 2.2.0, pyproj 3.8.0), including the
  night-rejection path.

## #18 GeoLocator — scoped review outcome (2026-10-20)

- App: `samhita-alla/geolocator`, MIT (upstream `LICENSE`), last commit
  `80f270a4c6e962b5542545127edfd320d7168dc9` (2022-12-27). It is an
  end-to-end demo (PyTorch Lightning, ONNX Runtime, BentoML, Gradio) wrapped
  around the ECCV-2018 GeoEstimation ResNet; the only image-geolocation
  capability worth adopting is that pre-trained model.
- Weights: the app's notebook and service download
  `epoch.014-val_loss.18.4833.ckpt` and `hparams.yaml` from the
  `TIBHannover/GeoEstimation` `pytorch` release. Re-checked 2026-10-20: the
  official repository's README states that **all source code and model
  weights have been removed** from the repository and its entire history,
  "after careful consideration of the ethical and societal risks", retains the
  repository for documentation only, and explicitly "refrains from further
  public release of the implementation". Both release URLs used by the app
  return HTTP 404.
- The `samhita-alla/GeoEstimation` fork still exists, but building from it
  would contradict the upstream authors' stated withdrawal; Aletheia does not
  use it. The app's video path additionally depends on YouTube-DL and network
  access, which would require an authorized live target; none exists for this
  source.
- **Outcome:** recorded as a blocker, no code and no manifest entry. No owner
  action is required; an owner who wants this capability would have to obtain
  explicit permission from the GeoEstimation authors, which this campaign does
  not do. The source remains one of the 29 not-yet-wired rows.

## #20 crypttrace — scoped review outcome (2026-10-20)

- License: MIT (upstream `LICENSE`), version 0.22.0, pinned at commit
  `cf60a88b8be43581186965d160114fdaf3022c62` (2026-10-17). The package is
  installed unmodified in its own image; the Aletheia driver is separate.
- **Premise corrected:** the earlier drop said "no importable API". The pinned
  package does expose `crypttrace.report.generate` / `report.collect` and the
  report writer emits a JSON sibling, so the re-review's condition (parseable
  output) is met without scraping the CLI's rich tables. The driver calls the
  library directly.
- Scope: **Bitcoin only**. `mempool.space` needs no key; the EVM path would
  require an Etherscan key and is out of scope. The optional USD column uses
  CoinGecko's keyless price endpoint. The seed is one base58/bech32 address,
  validated with `crypttrace.addresses.validate(address, "btc")`; a rejected
  address is a documented `invalid_target` and is never sent upstream.
- Bounds: depth 2, branching 3; at most 25 key findings and 25 top
  counterparties emitted; report `tree_text`, HTML and Markdown are discarded.
  The upstream fetcher spaces mempool.space calls by 0.25 s, caches in an
  ephemeral container-local SQLite file and retries 429s with backoff; the
  adapter itself never retries or caches. See
  `docker/crypttrace/RATE_LIMITS.md`.
- Interpretation: upstream labels, risk scores and exchange classifications
  are heuristics and lead generators, not proof of ownership, identity or
  wrongdoing. A public-blockchain address is pseudonymous; reaching a labelled
  address is not attribution. The adapter requires an authorization assertion
  for a real trace.
- **No live target is on file** for a crypto address, so Gate 2 cannot authorize
  a live trace. The CI evidence is fixture-based: health, an offline 8-check
  selftest (package import, address validation, report API, normalization,
  bounds), and a synthetic report parsed under `--network none`.
- **Outcome:** built and CI-verified — run `39466252253` on commit `446ccab2b9c819066dc67638f16b867bc074bd94`
  (parser 57/57; 1132 passed; capture 81/81, including
  `phase17-crypttrace-health` (`ok`), `phase17-crypttrace-selftest` (8/8) and
  `phase17-crypttrace-normalize` under `--network none`). Driver health and
  selftest were also validated locally against the exact package version in an
  isolated venv.

## #21 researcher_ids — scoped review outcome (2026-10-20)

- **Licence / terms:** both sub-sources are public and keyless. Wikidata data is
  CC0 1.0, accessed through the MediaWiki Action API under the Wikimedia API
  etiquette (descriptive User-Agent, bounded requests, `maxlag`). ORCID public
  data is CC0 1.0, accessed through the public API v3.0; no client credential is
  required. The reviewed contracts were read from the official API
  documentation on 2026-10-20; see `docker/researcher_ids/RATE_LIMITS.md`.
- **Scope:** one `person_name` seed. Wikidata gets one `wbsearchentities` search
  (`language=en`, `type=item`, `limit=5`) plus at most two `wbgetentities` reads
  (the five hits and at most 40 referenced IDs). ORCID gets one
  `expanded-search` request (`rows=5`). A two-token name uses
  `given-names:"<first>" AND family-name:"<last>"`; a one-token name uses
  `text:"<name>"`. Middle names are not guessed into the ORCID query.
- **Data minimisation:** only public fields are normalized — Wikidata QID,
  label, description, aliases, instance-of, occupation, birth date/place,
  citizenship, gender, given/family name, public ORCID/VIAF/ISNI/GND
  identifiers, official website and public Twitter handle; ORCID iD,
  given/family/credit name, other names and public institution names. ORCID
  responses can contain an `email` array; the runner deliberately discards it.
  No credential, account, email address, or private profile field is accepted
  or emitted.
- **Interpretation:** a name search is a lead, not identity proof. Common names
  collide, both services rank by their own relevance, and neither asserts that
  a result is the person the operator meant. Findings carry lead-only
  confidence (0.4 for a human Wikidata hit, 0.25 for other Wikidata hits, 0.4
  for ORCID, 0.2 for the run summary). The adapter never merges a Wikidata QID
  with an ORCID iD automatically.
- **Bounds:** 30-second timeout, 8 MB response cap, no retries, pagination,
  cache, or proxy rotation. A source failure is non-fatal and produces a
  `partial` document with the other source's results and a bounded error list.
- **No live target is on file** for a person name. Verification is
  fixture-based: `tests/fixtures/researcher_ids.json`, parser/driver tests, an
  offline 8-check selftest, and Docker health/normalize cases under
  `--network none`.
- **Outcome:** built and CI-verified — run `39484536317` on commit
  `ceaf595a6edc8bee46964ed5ccf273cb06f2b9c6` (parser 58/58; 1141 passed;
  capture 84/84; egress adapters=58 network_required=51 wired=51; results 84
  entries, 0 nonzero; storage 6/6). The three `phase17-researcher-ids-*` cases
  returned 0 under `--network none`; no live source lookup occurred.

## #22 weather — scoped review outcome (2026-10-20)

- **Licence / terms:** Open-Meteo's free API is keyless but **non-commercial**,
  with published limits of 600 calls/minute, 5,000/hour and 10,000/day per
  IP/application; its data is CC-BY 4.0. Aletheia is a free/open-source,
  non-commercial project. A downstream commercial deployment must use
  Open-Meteo's paid API; the adapter does not provide that path. Every document
  and finding carries `Weather data by Open-Meteo.com (CC-BY 4.0)`. Terms and
  endpoints were read from the official site on 2026-10-20; see
  `docker/weather/RATE_LIMITS.md`.
- **Scope:** one `geolocation` seed, either `latitude,longitude` for current
  conditions or `latitude,longitude,YYYY-MM-DD` for one day. Past dates use the
  historical archive endpoint; today/future dates use the forecast daily
  endpoint. One HTTP request per run; 30-second timeout; 4 MB response cap; no
  retries, pagination, cache, or proxy rotation.
- **Data minimisation:** only coordinates and a date are sent. No seed identity,
  account, credential, or personal data is included, and no secret exists to
  leak. The normalized document records the requested point, the returned model
  grid point and elevation, units, and at most 31 daily values per field.
- **Interpretation:** weather at the nearest grid point is environmental
  context. It can corroborate or contradict an image's claimed time/place but
  cannot prove that an image was taken there or then; grid resolution, elevation
  differences and forecast error matter. The adapter reports context only.
- **No live target is on file** for a coordinate. Verification is fixture-based:
  `tests/fixtures/weather.json`, parser/driver tests for forecast and archive
  normalization, an offline 9-check selftest, and Docker health/normalize cases
  under `--network none`.
- **Outcome:** built and CI-verified — run `39487437707` on commit
  `503b4311e9c513697a1b26b3d5d2ccf362a09146` (parser 59/59; 1149 passed;
  capture 87/87; egress adapters=59 network_required=52 wired=52; results 87
  entries, 0 nonzero; storage 6/6). The three `phase17-weather-*` cases returned
  0 under `--network none`; no live source lookup occurred.
