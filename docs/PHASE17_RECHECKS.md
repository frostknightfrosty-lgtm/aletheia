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
