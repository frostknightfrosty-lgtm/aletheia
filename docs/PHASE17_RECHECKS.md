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
