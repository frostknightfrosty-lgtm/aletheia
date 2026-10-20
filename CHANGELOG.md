# Changelog

## 2026-10-20 — P17.13: weather adapter (Open-Meteo forecast + historical archive)

Every number below is copied from the downloaded artifact
`ci-artifacts-39487437707` (run `39487437707`, commit `503b431`).

- `PARSER PREFLIGHT: PASS — 59/59 adapters have parser coverage` (58 → 59).
- `"console_summary": "1149 passed, 1 warning"` with `"junit_total": 1149`,
  `"skipped_in_ci": []`, `"ok": true`.
- `DOCKER CAPTURE: PASS — 87/87 cases captured`, including
  `phase17-weather-health` (stdout `ok`), `phase17-weather-selftest` (9/9
  offline checks) and `phase17-weather-normalize`, which parses a synthetic
  saved response under `--network none`; no live weather lookup was run.
- `egress-scenario.json`: `adapters=59 network_required=52 wired=52`.
- `storage-conformance.json`: 6/6 backends, `required_all: true`.
- `results.json`: 87 entries, 0 nonzero return codes.
- New source contract: no key; free API is non-commercial only (600/minute,
  5,000/hour, 10,000/day); CC-BY 4.0 attribution is carried on every finding;
  one request per run. See `docker/weather/RATE_LIMITS.md` and
  `docs/PHASE17_RECHECKS.md` #22. This covers both the Open-Meteo and
  historical-weather horizon items.

## 2026-10-20 — P17.13: researcher_ids adapter (Wikidata + ORCID)

Every number below is copied from the downloaded artifact
`ci-artifacts-39484536317` (run `39484536317`, commit `ceaf595`).

- `PARSER PREFLIGHT: PASS — 58/58 adapters have parser coverage` (57 → 58).
- `"console_summary": "1141 passed, 1 warning"` with `"junit_total": 1141`,
  `"skipped_in_ci": []`, `"ok": true`.
- `DOCKER CAPTURE: PASS — 84/84 cases captured`, including
  `phase17-researcher-ids-health` (stdout `ok`),
  `phase17-researcher-ids-selftest` (8/8 offline checks, including the test
  that ORCID email arrays are discarded) and
  `phase17-researcher-ids-normalize`, which parses a synthetic combined
  document under `--network none`; no live source lookup was run.
- `egress-scenario.json`: `adapters=58 network_required=51 wired=51`.
- `storage-conformance.json`: 6/6 backends, `required_all: true`.
- `results.json`: 84 entries, 0 nonzero return codes.
- New source contract: Wikidata CC0 + ORCID public CC0, both keyless; one
  bounded query per source (max 5 results per source); ORCID email arrays are
  discarded; name matches are lead-only. See
  `docker/researcher_ids/RATE_LIMITS.md` and
  `docs/PHASE17_RECHECKS.md` #21.

## 2026-10-20 — P17.11: crypttrace adapter (source #20)

Every number below is copied from the downloaded artifact
`ci-artifacts-39466252253` (run `39466252253`, commit `446ccab`).

- `PARSER PREFLIGHT: PASS — 57/57 adapters have parser coverage` (56 → 57).
- `"console_summary": "1132 passed, 1 warning"` with `"junit_total": 1132`,
  `"skipped_in_ci": []`, `"ok": true` — 10 new tests (eight adapter/driver
  tests, the container health test and the manifest parametrization), none
  skipped in CI (1122 → 1132).
- `DOCKER CAPTURE: PASS — 81/81 cases captured`, including the three new
  cases `phase17-crypttrace-health` (stdout `ok`, pin file true, package
  `0.22.0`), `phase17-crypttrace-selftest` (8/8 checks: package import, Bitcoin
  address validation, report API, normalization and bounds) and
  `phase17-crypttrace-normalize`, which parses a synthetic report under
  `--network none`; no live trace was run.
- `egress-scenario.json`: `adapters=57 network_required=50 wired=50` (the new
  adapter declares `network_required=True` and is policy-wired).
- `storage-conformance.json`: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"required_all": true`, `"ok": true`.
- `results.json`: 81 entries, 0 nonzero return codes.
- Scope: `SeedType.CRYPTO_ADDRESS`, Bitcoin only, no API key. The driver calls
  the pinned library's `crypttrace.report.generate(address, "btc", depth=2,
  branching=3)` and reduces its JSON to a run summary, at most 25 labelled
  key findings and 25 top counterparties. Hosts are mempool.space (history)
  and CoinGecko (optional BTC/USD price). Labels, risk scores and exchange
  classifications are upstream heuristics and leads, not proof of ownership or
  wrongdoing; the upstream fetcher caches in an ephemeral container-local
  SQLite file and retries 429s with backoff, while the adapter never retries
  or caches. See `docker/crypttrace/RATE_LIMITS.md`.
- `§A 20` flipped; manifest `crypttrace` is `verified-fixture`; counts are now
  **83 of 111** wired and **57 registered adapters**, with **28 remaining**.
  No live target exists for this source, so the evidence is fixture-based.

## 2026-10-20 — P17.11: pybdshadow adapter (source #16)

Every number below is copied from the downloaded artifact
`ci-artifacts-39457146650` (run `39457146650`, commit `4505ae5`).

- `PARSER PREFLIGHT: PASS — 56/56 adapters have parser coverage` (55 → 56:
  the seventh Phase 17 registry addition).
- `"console_summary": "1122 passed, 1 warning"` with `"junit_total": 1122`,
  `"skipped_in_ci": []`, `"ok": true` — 10 new tests (eight adapter/driver
  tests, the container health test and one manifest-driven parametrization),
  none skipped in CI (1112 → 1122).
- `DOCKER CAPTURE: PASS — 78/78 cases captured`, including the three new
  cases `phase17-pybdshadow-health` (stdout `ok`, with `pin_file: true`,
  package `0.3.5`, geopandas `1.2.0`, pyproj `3.8.0`, shapely `2.2.0`),
  `phase17-pybdshadow-selftest` (8/8 checks, including a real footprint shadow
  computation and the night-rejection path) and `phase17-pybdshadow-run`, a
  synthetic footprint run through the real library.
- `egress-scenario.json`: `adapters=56 network_required=49 wired=49` (the new
  source is offline, so the wired set is unchanged).
- `storage-conformance.json`: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"required_all": true`, `"ok": true`.
- `results.json`: 78 entries, 0 nonzero return codes.
- Scope: new file-seed input (`SeedType.FILE_PATH`) carrying 1–200 building
  footprint polygons with heights and one UTC datetime; the pinned pybdshadow
  library (BSD-3-Clause, 0.3.5, commit `e2665ee`) runs entirely offline.
  Per-building outputs are shadow summaries (bbox, centroid, geodesic area,
  polygon/vertex counts), not a confirmed location; bounds are 1,000,000 input
  bytes, 1–200 buildings, 4–1,000 vertices, heights 0.1–1,000 m, years
  1900–2100, no holes. Holes are rejected because the upstream routine uses
  the exterior ring. See `docker/pybdshadow/RATE_LIMITS.md`.
- `§A 16` flipped; manifest `pybdshadow` is `verified-fixture`; counts are now
  **82 of 111** wired and **56 registered adapters**, with **29 remaining**.

## 2026-10-20 — P17.11: ShadowFinder adapter (source #15)

Every number below is copied from the downloaded artifact
`ci-artifacts-39448325747` (run `39448325747`, commit `5ddf240`).

- `PARSER PREFLIGHT: PASS — 55/55 adapters have parser coverage` (54 → 55:
  the sixth Phase 17 registry addition).
- `"console_summary": "1112 passed, 1 warning"` with `"junit_total": 1112`,
  `"skipped_in_ci": []`, `"ok": true` — 12 new tests (10 adapter/driver tests,
  the container health test, and one manifest-driven parametrization), none
  skipped in CI (1100 → 1112).
- `DOCKER CAPTURE: PASS — 75/75 cases captured`, including the two new cases
  `phase17-shadowfinder-health` and `phase17-shadowfinder-selftest` (under
  `--network none`; health stdout `ok`, with `pin_file: true`,
  `grid_resolution_deg: 0.5`, `grid_cells: 208800`, `network_imports: []`, and
  package `0.7.1`; the selftest passed 9/9 checks, including a real 3×3 solar
  computation with 9 finite cells).
- `egress-scenario.json`: `adapters=55 network_required=49 wired=49` (the new
  source is offline, so the wired set is unchanged).
- `storage-conformance.json`: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"required_all": true`, `"ok": true`.
- `results.json`: 75 entries, 0 nonzero return codes.
- Scope: new `SeedType.SHADOW_OBSERVATION` (object height, shadow length, UTC
  datetime); the pinned Bellingcat ShadowFinder library (MIT, tag v0.7.1,
  commit `215485a`) runs entirely offline over its shipped 0.5° grid. Outputs
  are coarse 1° possibility bins (bbox, centroid, best cell, relative
  difference, cell count), not a confirmed location; tolerance 0.10 (max 0.5),
  1° bins (0.25–5°), top 20 regions (max 50), grid step 1 (max 4), years
  1900–2100, polar regions excluded. No coordinate or measurement leaves the
  container; no request library is imported; no owner action is needed. See
  `docker/shadowfinder/RATE_LIMITS.md`.
- `§A 15` flipped; manifest `shadowfinder` is `verified-fixture`; counts are now
  **81 of 111** wired and **55 registered adapters**, with **30 remaining**.

## 2026-10-20 — P17.11: tracelines adapter (source #14)

Every number below is copied from the downloaded artifact
`ci-artifacts-39416003189` (run `39416003189`, commit `0ac22ed`).

- `PARSER PREFLIGHT: PASS — 54/54 adapters have parser coverage` (53 → 54: the
  fifth Phase 17 registry addition).
- `"console_summary": "1100 passed, 1 warning"` with `"junit_total": 1100`,
  `"skipped_in_ci": []`, `"ok": true` — 11 new tests (the 9 driver/parser
  tests, the container health test, and one manifest-driven parametrization),
  none skipped in CI (1089 → 1100).
- `DOCKER CAPTURE: PASS — 73/73 cases captured`, including the two new cases
  `phase17-tracelines-health` and `phase17-tracelines-selftest` (return code 0
  under `--network none`; health stdout `ok` with `pin_file: true`, pinned
  checkout `0.2.0`, `max_retries: 1`, `cache_enabled: false`,
  `streetlevel_installed: false`, `tls_static: true`, honest UA, provider
  bindings `kartaview`/`mapillary`; the selftest ran 10/10 checks);
  results.json: 73 entries, 0 nonzero return codes; the egress scenario
  reported `adapters=54 network_required=49 wired=49` (all nine checks ok;
  chain `valid: true`); storage-conformance.json: `"required_all": true`,
  `"ok": true`, `"unconfigured": []` (6/6 backends passing).
- What landed: `docker/tracelines/` gained a driver and image over the pinned
  upstream (commit `99257f0519b30ce7d890db25252f6cf440fa102e`; tag v0.2.0,
  released 2026-07-14; AGPL-3.0-or-later), operated unmodified in its own image
  (the SearXNG copyleft precedent). Only the documented providers are bound:
  Mapillary sequence vector tiles (free `MAPILLARY_TOKEN`; recorded skip
  without it) and keyless KartaView sequences. The Google provider is excluded
  structurally: `streetlevel` is never installed, and the driver refuses to run
  if it becomes importable. One point seed, a derived ≤300 m bbox, one to four
  Mapillary z14 tile requests, and at most two KartaView sequence requests; no
  retries (`max_retries=1`), no disk cache, no pagination. Coverage is
  summarized in memory (segment length, point count, centroid/endpoints,
  capture date) with Mapillary/KartaView CC-BY-SA 4.0 attribution; no geometry
  is written or redistributed. TLS is never relaxed. No authorized point seed
  exists, so the adapter ships **fixture-verified only** — no live requests
  were made.
- Build defect found by CI (recorded, not hidden): the unit's first real run
  (`39412502739`, attempt 4) failed in the image build with
  `ERROR: No matching distribution found for networkx==3.7` — the Dockerfile
  used `python:3.11-slim-bookworm`, while the pinned `networkx==3.7` requires
  Python ≥3.12. Fixed in `0ac22ed` by building on `python:3.12-slim-bookworm`;
  this run verifies the fixed tree. The failures before that were the CI
  capacity block, not this defect.
- Docs/state: §A 14 flipped in `SOURCE_COMPLETENESS.md` (80 of 111 wired; 54
  adapters; 31 remain); the `tracelines` manifest entry cites the run; §0 of
  `USER_ACTIONS.md` marked resolved (the repository was made public) and the
  parked queue removed; `HANDOFF.md` updated.

## 2026-10-20 — P17.11: PicImageSearch adapter (source #13)

Every number below is copied from the downloaded artifact
`ci-artifacts-39404418732` (run `39404418732`, commit `19db818`).

- `PARSER PREFLIGHT: PASS — 53/53 adapters have parser coverage` (52 → 53: the
  fourth Phase 17 registry addition).
- `"console_summary": "1089 passed, 1 warning"` with `"junit_total": 1089`,
  `"skipped_in_ci": []`, `"ok": true` — 16 new tests (the 14 driver/parser
  tests, the container health test, and one manifest-driven parametrization),
  none skipped in CI (1073 → 1089).
- `DOCKER CAPTURE: PASS — 71/71 cases captured`, including the two new cases
  `phase17-picimagesearch-health` and `phase17-picimagesearch-selftest`
  (return code 0 under `--network none`; health stdout `ok` with
  `engine_bindings: 5`, `ua_honest: true`, `tls_verified: true`, pinned
  checkout `3.12.11`; the selftest ran 9/9 checks); results.json: 71 entries,
  0 nonzero return codes; the egress scenario reported
  `adapters=53 network_required=48 wired=48`; storage-conformance.json:
  `"required_all": true`, `"ok": true`, `"unconfigured": []` (6/6 backends
  passing).
- What landed: `docker/picimagesearch/` gained a driver and image that run only
  the reviewed keyless engines of the pinned upstream (commit
  `784713e546273a09aae4b247a8b6f798825efafa`; self-reported version 3.12.11;
  MIT): IQDB, 3D IQDB, Ascii2D colour search, TraceMoe, and AnimeTrace — one
  request each — plus the official SauceNAO JSON API only when
  `SAUCENAO_API_KEY` is set (recorded skip otherwise). The consumer-web
  scrapers (Google, Google Lens, Yandex, Bing, Baidu), the token-refresh
  Copyseeker scraper, the Turnstile-blocked Lenso client, the TinEye web-app
  scrape, and the adult-gallery EHentai engine are never imported; reasons are
  in `docker/picimagesearch/RATE_LIMITS.md`. Two fail-closed deviations: the
  package's hardcoded browser user agent is replaced with the fixed honest
  `Aletheia/0.9.0 (picimagesearch)` agent (re-checked per engine before every
  run), and TLS verification is never disabled. No authorized live image
  target exists, so the adapter ships **fixture-verified only** — no live
  requests were made. Explicit authorization is required per target image.
- Docs/state: §A 13 flipped in `SOURCE_COMPLETENESS.md` (79 of 111 wired; 53
  adapters; 32 remain); the `picimagesearch` manifest entry cites the run;
  optional owner item recorded — a SauceNAO API key would enable that engine
  (`docs/USER_ACTIONS.md`).

## 2026-10-19 — P17.11: VENOM adapter (source #12)

Every number below is copied from the downloaded artifact
`ci-artifacts-39196608448` (run `39196608448`, commit `0015ea4`).

- `PARSER PREFLIGHT: PASS — 52/52 adapters have parser coverage` (51 → 52: the
  third Phase 17 registry addition).
- `"console_summary": "1073 passed, 1 warning"` with `"junit_total": 1073`,
  `"skipped_in_ci": []`, `"ok": true` — 15 new tests (the 13 driver/parser
  tests, the container health test, and one manifest-driven parametrization),
  none skipped in CI (1058 → 1073).
- `DOCKER CAPTURE: PASS — 69/69 cases captured`, including the two new cases
  `phase17-venom-health` and `phase17-venom-selftest` (return code 0 under
  `--network none`; the selftest ran 7/7 checks); results.json: 69 entries,
  0 nonzero return codes; the egress scenario reported
  `adapters=52 network_required=47 wired=47`; storage-conformance.json:
  `"required_all": true`, `"ok": true`, `"unconfigured": []` (6/6 backends
  passing).
- What landed: `docker/venom/` gained a driver and image that run only the
  reviewed keyless module set of the pinned checkout (commit
  `6fa3a483abc9cb0a1d96567e33b2919be59522c6`; 29 upstream classes / 30 driver
  bindings — 5 email / 12 username / 13 domain modules, one query each).
  Keyed services (HIBP, BreachDirectory, LeakCheck, OSINTLeak, IntelX,
  Phonebook, Hunter, NumLookup), the borrowed-key Leak-Lookup module, the
  Dehashed scrape, the Holehe/Google login-form probes, the raw-socket
  SSL/RBL checks, the plain-HTTP ip-api path, the DuckDuckGo scrape, the AI
  agent, dorks/export/render, and the web UI are never imported; reasons are
  in `docker/venom/RATE_LIMITS.md`. `VenomAdapter` adds email, username, and
  domain input paths. Two documented fail-closed deviations: rotating browser
  user agents are replaced with the fixed honest `Aletheia/0.9.0 (venom)`
  agent on every module object, and upstream's hardcoded `ssl=False` is
  overridden by a session class that forces certificate verification.

## 2026-10-18 — P17.11: tiktok-hashtag-analysis adapter (source #4)

Every number below is copied from the downloaded artifact
`ci-artifacts-39174382751` (run `39174382751`, commit `fedfd64`).

- `PARSER PREFLIGHT: PASS — 51/51 adapters have parser coverage` (50 → 51: the
  second Phase 17 registry addition).
- `"console_summary": "1058 passed, 1 warning"` with `"junit_total": 1058`,
  `"skipped_in_ci": []`, `"ok": true` — 12 new tests (the 10 driver/parser
  tests, the container health test, and one manifest-driven parametrization),
  none skipped in CI (1046 → 1058).
- `DOCKER CAPTURE: PASS — 67/67 cases captured`, including the two new cases
  `phase17-tiktok-hashtag-health` and `phase17-tiktok-hashtag-selftest`
  (return code 0 under `--network none`; the selftest ran 7/7 checks including
  the pinned-checkout import); results.json: 67 entries, 0 nonzero return
  codes; storage-conformance.json: `"required_all": true`, `"ok": true`,
  `"unconfigured": []` (6/6 backends passing).
- What landed: `docker/tiktok_hashtag/` gained a driver and image that run the
  pinned Bellingcat library (commit
  `2a4af674efc4af7c7d592053ec3f475555f37694`) headless-only, calling
  `_fetch_hashtag_data(..., headed=False)` directly so the upstream headed
  retry is structurally unreachable. The dependency's unconditional stealth
  patching is neutralized with a no-op before any session is created (fail
  closed; decision recorded in `docs/PHASE17_RECHECKS.md`), and TikTok
  bot-detection responses are recorded honestly as `blocked` — no retry loop,
  no cookies, no challenge handling. `TiktokHashtagAdapter` adds the
  `SeedType.HASHTAG` input path; the earlier `social_profile` drop note stands
  and now points to the standalone adapter entry.

## 2026-10-18 — P17.11: Zehef email adapter (source #2)

Every number below is copied from the downloaded artifact
`ci-artifacts-39171286556` (run `39171286556`, commit `22d3ddc`).

- `PARSER PREFLIGHT: PASS — 50/50 adapters have parser coverage` (49 → 50: the
  first Phase 17 registry addition).
- `"console_summary": "1046 passed, 1 warning"` with `"junit_total": 1046`,
  `"skipped_in_ci": []`, `"ok": true` — 12 new tests (the 10 driver/parser
  tests, the container health test, and one manifest-driven parametrization),
  none skipped in CI (1034 → 1046).
- `DOCKER CAPTURE: PASS — 65/65 cases captured`, including the two new cases
  `phase17-zehef-health` and `phase17-zehef-selftest` (return code 0 under
  `--network none`; the selftest ran 7/7 checks including the pinned-checkout
  import); results.json: 65 entries, 0 nonzero return codes; storage-
  conformance.json: `"required_all": true`, `"ok": true`, `"unconfigured": []`
  (6/6 backends passing).
- What landed: `docker/zehef/` gained a driver and image that run only the 17
  account-registration modules of the pinned checkout (Zehef 2.2.1, commit
  `5b0c120efe846eae944dfea9410f925ca3036103`). The paste-dump module (Google
  search scraping), the HudsonRock stealer-log module and the random
  email-combination generator are never invoked, with reasons in
  `docker/zehef/RATE_LIMITS.md`. `ZehefAdapter` emits only positive
  registration signals plus allowlisted public account URLs (https
  github.com / flickr.com / gravatar.com); avatar and id detail fields are
  deliberately dropped. The earlier `social_profile` drop stands as history
  and now points to the standalone adapter entry.

## 2026-10-18 — P17.11: Broń Vault loopback sub-source (source #11)

Every number below is copied from the downloaded artifact
`ci-artifacts-39168364470` (run `39168364470`, commit `d3e7d16`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (the
  sub-source extends `leak_checkers`; no new adapter).
- `"console_summary": "1034 passed, 1 warning"` with `"junit_total": 1034`,
  `"skipped_in_ci": []`, `"ok": true` — 4 new tests (route-contract
  conformance, email/username input mapping, the unconfigured-skip plus
  non-loopback refusal, and the loopback selftest), none skipped in CI
  (1030 → 1034).
- `DOCKER CAPTURE: PASS — 63/63 cases captured`, including the new
  `phase17-leak-checkers-bron-vault` case, which runs the client's loopback
  selftest under `--network none`.
- What landed: `docker/leak_checkers/runner.py` gained `bron-vault` as a
  third sub-source. The route contract is pinned to release v1.4.0, commit
  `6bfdcc0196ac90ed38a35a1099697497680c1666`: `POST
  /api/v1/search/credentials` with the `X-API-Key` header and
  `includePasswords=false`. The client refuses any non-loopback host before
  opening a socket, refuses off-host redirects, bypasses environment proxies,
  never requests full passwords, and reports a documented skip until
  `BRON_VAULT_URL` and `BRON_VAULT_API_KEY` are set. The README names GET for
  the search route while the route file implements POST — the client follows
  the route file; the discrepancy is recorded in
  `docker/leak_checkers/RATE_LIMITS.md`.

## 2026-10-18 — P17.11: CipherScan sub-source (source #36)

Every number below is copied from the downloaded artifact
`ci-artifacts-39167510546` (run `39167510546`, commit `f785aa7`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (the
  sub-source extends `ssl_tls`; no new adapter).
- `"console_summary": "1030 passed, 1 warning"` with `"junit_total": 1030`,
  `"skipped_in_ci": []`, `"ok": true` — 9 new tests (subject/details
  extraction, the JSON contract, tolerance parsing, selftest reporting), none
  skipped in CI (1021 → 1030).
- `DOCKER CAPTURE: PASS — 62/62 cases captured`, including the new
  `phase17-ssl-tls-cipherscan` case, which runs the pinned checkout's selftest
  offline under `--network none`.
- What landed: `docker/ssl_tls/runner.py` gained `cipherscan` as a sixth
  sub-source. The project publishes no releases or tags, so the checkout is
  pinned to commit `30bd23938853d68b51c2ebe4bcc922cc3113c5e2` (verified with
  `git rev-parse` at build time); the tolerance-test dependencies are pinned to
  tlslite-ng `c93df82603ab4a72c8d65645a3aeee73eeb24b3f` (v0.8.2) and
  python-ecdsa `bd66899550d7185939bf27b75713a2ac9325a9d3` (0.19.2). The tool is
  invoked at its real path (no symlink — `cscan.sh` resolves helper files from
  `dirname $0`), JSON output (`-j`) is parsed into suite/config/tolerance
  records, and the source is reported through the same documented-skip pattern
  when the binary is absent.

## 2026-10-18 — P17.11: SearXNG self-hosted sub-source (source #31)

Every number below is copied from the downloaded artifact
`ci-artifacts-39166656036` (run `39166656036`, commit `1c18b80`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (the
  sub-source extends `search_engines`; no new adapter).
- `"console_summary": "1021 passed, 1 warning"` with `"junit_total": 1021`,
  `"skipped_in_ci": []`, `"ok": true` — 10 new tests (subject/details
  extraction, the documented search shape, boot failure, settings generation,
  selftest reporting), none skipped in CI (1011 → 1021).
- `DOCKER CAPTURE: PASS — 61/61 cases captured`, including the new
  `phase17-search-engines-searxng` case, which boots the pinned instance
  offline under `--network none`.
- What landed: `docker/search_engines/runner.py` gained `searxng` as a third
  sub-source operated inside the same image: upstream pinned to commit
  `1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4` (AGPL-3.0-or-later, operated
  unmodified), engines kept to `duckduckgo`, `brave` and `wikipedia` via the
  documented `keep_only` mechanism, JSON enabled in the generated settings,
  `SEARXNG_SECRET` randomized at boot, and live runs route the instance's
  engine requests through the same egress proxy as every other outbound
  request (loopback queries never use it). The source reports its documented
  skip when no live instance is available.

## 2026-10-18 — P17.11: Unpaywall DOI-keyed live path (source #33)

Completes the first Wave-A build of the source-completeness directive. Every
number below is copied from the downloaded artifact `ci-artifacts-39160798771`
(run `39160798771`, commit `139d141`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (no new
  adapter — the DOI route extends `academic_search`).
- `"console_summary": "1009 passed, 1 warning"` with `"junit_total": 1009`,
  `"skipped_in_ci": []`, `"ok": true` — 4 new tests (DOI extraction, the live
  DOI call, the missing-email skip, the DOI-record parse), none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`; storage-conformance.json
  `"required_all": true`, `"ok": true`, `"unconfigured": []`.
- What landed: `docker/academic_search/runner.py` queries the documented DOI
  endpoint (`GET /v2/:doi`, contact email required) only for DOI-shaped inputs
  (`10.<registrant>/<suffix>`, optionally behind a `doi:` prefix or a doi.org
  URL), keeping the full vendor response as raw evidence; the adapter parses
  DOI records as `unpaywall_doi_record`; `UNPAYWALL_EMAIL` joined `secret_env`
  and both live workflows; RATE_LIMITS.md carries the verbatim contract and
  the 2026-10-18 probe (HTTP 422 refuses a placeholder address). Name-based
  inputs keep the documented skip reason and build no URL.

## 2026-10-18 — P17.10: live cascade runner + first live dispatch (repair)

The runner that executes one audited cascade run against the live adapters,
and the campaign's first live dispatch on the authorized target
`username:frost2233`. Every number below is copied from downloaded artifacts;
the live dispatch's failure is recorded verbatim.

- CI (run `39159820872`, commit `dc44fc5` + docs `39680b0`): `PARSER
  PREFLIGHT: PASS — 49/49 adapters have parser coverage`; `"console_summary":
  "1005 passed, 1 warning"` with `"junit_total": 1005`, `"skipped_in_ci": []`,
  `"ok": true`; `DOCKER CAPTURE: PASS — 60/60 cases captured`;
  storage-conformance.json `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: one audited run per cascade (`cascade/runner.py`) — fixture
  observer for I/O-free dry-runs, live `AdapterObserver` reusing the egress
  proxy/audit-chain patterns; the manifest `cascade` section carries the
  verbatim authorization assertion and the scheduler checkpoint; ledger,
  trail, dossier, coverage and next-actions artifacts under
  `runs/<id>/cascade/`; `aletheia cascade run` CLI; a `live-cascade.yml`
  dispatch workflow; 7 runner tests.
- First live dispatch (run `39159843080`): leak_checkers, maigret,
  reddit-api, sherlock, social_username and youtube-api completed; instaloader
  timed out (`container timed out after 120s`, recorded); a later instaloader
  pivot then crashed the run on its per-invocation egress network —
  `DockerCommandError: wiring command failed (exit 1): docker network create
  --internal aletheia-egress-net-instaloader` / `Error response from daemon:
  network with name aletheia-egress-net-instaloader already exists`.
- Repair: one egress session per adapter for the whole run (network names are
  adapter-derived), incremental proxy-entry chaining, wiring-start failures
  recorded as blocked and never retried or run unwired, `close()` teardown in
  `run_cascade`; 2 regression tests. Repair verified — run `39161437568`
  green: `PARSER PREFLIGHT: PASS — 49/49`; `"console_summary": "1011 passed,
  1 warning"` with `"skipped_in_ci": []`, `"ok": true`; `DOCKER CAPTURE: PASS
  — 60/60`; storage `ok: true`.
- **Live cascade green** (re-dispatch on the repaired tree `9a9cb38`, run
  `39161463451`): `stop_reason=saturated`; `expansions=1`;
  `trail_digest=f2af6529df6125190d1b88994be038b941b60459dcd2598bd88a511ff60c0247`;
  `coverage_ok=True`; `verify-chain.log`: `valid:
  e86fefe0-ff40-4c98-b7e8-9d846b59460b`, `chain tip:
  feaad1a7811bedd9b0a917f05dbe776388bcfe85542d3d6d44be80cd626b5edc`, `manifest
  anchor: verified`. 6 of 7 expected adapters ran; instaloader timed out in
  both rounds and was recorded (`cascade_adapter_error x2`) without killing
  the run — exactly the failure class the repair closed. 1,146 egress
  requests were chained; 1 identity cluster now awaits the owner
  (`USER_ACTIONS.md` §3).

## 2026-10-18 — P17.9: deterministic cascade engine + synthetic-world suites

The pivot cascade's execution core: a deterministic engine over an injectable
observer, with the falsification-first merge order and a replayable decision
ledger. Every number below is copied from the downloaded artifact
`ci-artifacts-39159218589` (run `39159218589`, commit `e9b8de5`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (no new
  adapters in this step).
- `"console_summary": "998 passed, 1 warning"` with `"junit_total": 998`,
  `"skipped_in_ci": []`, `"ok": true` — 9 new tests over the previous 989,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `cascade/engine.py` — claims → gated pivots → VOI scheduler →
  evidence scoring and ACH → falsification-first confirmed merges; per-origin
  claim independence; parent-linked trail hops with a SHA-256 digest;
  hash-chained decision ledger; deterministic replay and resume; depth,
  budget and failure injection (blocked adapters, 429 egress refusals,
  hard-depth refusal) covered by synthetic-world, adversarial-collision and
  golden-digest determinism suites.

## 2026-10-18 — P17.8: cascade CLI, trail/dossier/coverage artifacts, redaction, purge

The cascade's review surface: CLI group, artifact builders, and the deletion
path. Every number below is copied from the downloaded artifact
`ci-artifacts-39158143846` (run `39158143846`, commit `ced6f08`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (no new
  adapters in this step).
- `"console_summary": "989 passed, 1 warning"` with `"junit_total": 989`,
  `"skipped_in_ci": []`, `"ok": true` — 21 new tests over the previous 968,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `aletheia cascade review|confirm|purge` (ledger replay and
  hash-chain verification, confirmation labels, case purge as the only
  deletion path); `trail.py` (validated parent-linked hops, SHA-256 digest
  over canonical hops); `dossier.py` (tiered clusters with evidence chains;
  `supported: false` never invents evidence); `coverage.py` (matched-but-
  neither-ran-nor-skipped, gate-evaluation, and balanced-egress audits);
  `next_actions.py` (checklist mirroring `docs/USER_ACTIONS.md`); `redact.py`
  (deterministic `redacted:<sha256-16>` tokens for person-identifier types).

## 2026-10-18 — P17.7: case memory, cache/TTL, re-audit diffs, labels, blind spots

Case memory and freshness infrastructure for re-audits. Every number below is
copied from the downloaded artifact `ci-artifacts-39157495630` (run
`39157495630`, commit `60bb0e6`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (registry
  unchanged).
- `"console_summary": "968 passed, 1 warning"` with `"junit_total": 968`,
  `"skipped_in_ci": []`, `"ok": true` — 24 new tests over the previous 944,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `case_store.py` (case snapshots as `section -> {key: JSON
  value}`, structural diffs, timeline); `source_cache.py` (TTL classes —
  profile 30d / dns 7d / configuration 7d — with freshness parity to the
  scheduler's freshness factor); `labels.py` (append-only confirmation
  labels, latest-wins views, `training_pairs` excluding unsure and scoreless
  rows, feeding `Calibrator`); `blind_spots.py` (curated blind-spot table
  citing only already-documented repo facts).

## 2026-10-18 — P17.6: VOI scheduler, adaptive budgets, stop policy, decision ledger

Budget-aware frontier management with a hash-chained audit trail. Every
number below is copied from the downloaded artifact
`ci-artifacts-39156855944` (run `39156855944`, commit `341f055`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (registry
  unchanged).
- `"console_summary": "944 passed, 1 warning"` with `"junit_total": 944`,
  `"skipped_in_ci": []`, `"ok": true` — 22 new tests over the previous 922,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `scheduler.py` (value-of-information ordering over the pivot
  frontier with reviewable constants — `DEPTH_PENALTY=0.6`,
  `DEFAULT_YIELD=1.0`, `DEFAULT_RARITY=0.5`, `DEFAULT_COST=1.0`,
  `MIN_COST=0.1`, `TIME_PRESSURE_FRACTION=0.25`, `SchedulerPolicy.min_voi=0.02`;
  per-type pivot caps; `(seed type, value)` dedup; fresh-TTL pivots refused
  at push with the ledger recording the refusal; depth escalation only when
  owner mode has seen a HARD gate; time pressure de-escalates depth by one);
  `ledger.py` (hash-chained decision ledger recording pivot proposals,
  grants, refusals, sweeps, and stops, verified by `verify()`).

## 2026-10-18 — P17.5: falsification pass, ACH hypothesis scoring, union-find merge graph

Consistency checks and conflict propagation the cascade trusts before it
merges or expands. Every number below is copied from the downloaded artifact
`ci-artifacts-39156241115` (run `39156241115`, commit `d561c9c`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (registry
  unchanged).
- `"console_summary": "922 passed, 1 warning"` with `"junit_total": 922`,
  `"skipped_in_ci": []`, `"ok": true` — 26 new tests over the previous 896,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `falsify.py` (cross-claim veto sweep reusing the evidence VETO
  rules, attribute contradictions on `date_of_birth`/`national_id`, era
  disjointness as a soft warning that never vetoes — era overlap is weak
  evidence, not proof of sameness); `ach.py` (competing-hypothesis assessment
  with a reviewable contribution table — +3/+2/+1/+0.5/−3 for the subject
  hypothesis, mirrored for `H_other`, halved for `H_shared` — a
  `DEFAULT_MARGIN = 1.0`, and the conservative tie order OTHER, SHARED,
  SUBJECT); `merge_graph.py` (confirmed-only merges, a conflict re-opens the
  chain and demotes the weakest link — path-local, tie-broken by
  `(score, lexicographic)` — with no silent split or merge); `claims.py`
  gained public `claim_origin_key`/`pair_origin_key` (evidence.py switched
  over); `scoring.py` gained the `source_grade_label` field and the E/F
  low-grade cap (the mechanism can only fire on explicitly attached E/F
  labels; an unrated source stays "not yet graded", never assumed
  unreliable).

## 2026-10-18 — P17.4: matchers, stdlib perceptual hashing, LR scoring, base-rate priors, calibration hook

The comparison and scoring engine the cascade evaluates with. Every number
below is copied from the downloaded artifact `ci-artifacts-39155284979` (run
`39155284979`, commit `db5f03e`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (registry
  unchanged).
- `"console_summary": "896 passed, 1 warning"` with `"junit_total": 896`,
  `"skipped_in_ci": []`, `"ok": true` — 56 new tests over the previous 840,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `matching.py` (diacritic folding, token-set and Jaro-Winkler
  comparison on `rapidfuzz`, Soundex against the NARA reference vectors,
  nickname expansion, temporal and graph overlap) — no new dependencies;
  `phash.py` (pure-stdlib PNG/BMP/PPM/PGM decoding plus aHash, dHash, and a
  DCT pHash, with Pillow only as an optional runtime fallback; JPEG stays
  unsupported in the core environment and is documented, not worked around);
  `scoring.py` (reviewable likelihood-ratio constants — HARD 50, STRONG 10,
  MEDIUM 3, WEAK 1.5 — vetoes never summed, tier rules with the review-gated
  "cannot clear a gate alone" cap, and a calibration hook that reports no
  probability until `core/calibration.py`'s `Calibrator` is actually
  trained); `priors.py` (entropy/rarity base-rate terms, explicitly
  `calibrated=False`); `evidence.py` (the claim-pair decision table,
  with shared-infrastructure guards: public mail domains and shared platform
  hosts never yield evidence).

## 2026-10-18 — P17.3: claim normalization, strong-key blocking, pivot extractors

The claim layer the evidence engine compares: normalized claims, blocking that
keeps comparisons out of O(n²), and the section-7 pivot gates. Every number
below is copied from the downloaded artifact `ci-artifacts-39154364738` (run
`39154364738`, commit `d7f035a`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (registry
  unchanged).
- `"console_summary": "840 passed, 1 warning"` with `"junit_total": 840`,
  `"skipped_in_ci": []`, `"ok": true` — 25 new tests over the previous 815,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed: `aletheia.cascade.claims` (claim model with an F6-unrated
  Admiralty default, canonicalization for seed-backed types only, strong-key
  blocking — email/phone/domain/exact-handle, with mail domains, URL hosts of
  shared platforms handled conservatively and oversized blocks reported, never
  silently dropped) and `aletheia.cascade.extractors` (claims → typed pivot
  seeds with the section-7 gates per record class, deterministic and total
  over every entity type; a fixture walk covers all rule types).

## 2026-10-18 — P17.2: cascade data models, descriptor-derived routing graph, seed autodetection

The first Phase 17 code step: the routing graph later cascade steps walk, plus
the seed layer that feeds it. Every number below is copied from the downloaded
artifact `ci-artifacts-39153749577` (run `39153749577`, commit `7900ce4`).

- `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage` (the registry
  did not change in this step; the graph is derived from the same 49
  descriptors).
- `"console_summary": "815 passed, 1 warning"` with `"junit_total": 815`,
  `"skipped_in_ci": []`, `"ok": true` — 29 new tests over the previous 786,
  none skipped in CI.
- `DOCKER CAPTURE: PASS — 60/60 cases captured`.
- storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
  "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
  `"required_all": true`, `"ok": true`.
- What landed (additive; no behavior change outside the new package):
  relationship types `SAME_AS_CONFIRMED` / `SAME_AS_EXCLUDED` /
  `PIVOTED_FROM`, cascade fields on `Provenance`, and the `IdentityTier` /
  `SourceGrade` / `Hypothesis` / `HypothesisAssessment` / `ClusterDecision` /
  `PivotCandidate` models; the new `aletheia.cascade` package with
  `routing.py` (bridge map over every entity type, terminal and autodetect
  classes, coverage validators with negative controls) and `seeds.py` (only
  validator-recognizable seed classes are auto-detected; canonicalization;
  first-appearance order; mask-based no-double-reporting).
- Honest limits recorded in the code: the seed detector never guesses
  names/companies/places from raw text (a regex cannot recognize arbitrary
  names honestly, so those are typed by the operator or extracted as claims
  later), and phone detection is conservative (international numbers need
  `+`, national ones need separators).

## 2026-10-18 — Authorized live self-audit of `username:frost2233` (run `39141366670`): round-3 repairs confirmed on the live path

The owner opened Gate 2 for one target with the assertion recorded verbatim in the run's
`MANIFEST.json` — `Self-audit: I am the owner of the Discord account with username frost2233
and I authorize an investigation of my own username across public, legal, open sources.` The
audit ran end to end in 37m19s on the tree that passed run `39139781693`
(https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39141366670; run directory
`983cc23b-f9f6-4ccd-8483-82f7e37738ba`). Every number below is copied from the downloaded
artifact `ci-artifacts-39141366670`.

- **`maigret` now proxies single-hop.** Its `EGRESS.jsonl` reads `total=585
  self_addressed=0` (run `39135219248`: `total=757 self_addressed=455`), statuses
  `{200: 575, 502: 6, 308: 1, 404: 1, 301: 2}`, `bytes>0 = 578`; the stdout error classes
  are `Too many errors of type "Bot protection" (16.11%)` and `Too many errors of type
  "Access denied" (3.14%)` — the `"Proxy" (46.17%)` and `"Unexpected" (31.43%)` classes of
  the previous run are gone. The same sweep returns **19 accounts** (was 5) with **extended
  info from 9 accounts** (was 2).
- **`sherlock` writes the file its parser reads.** The artifact contains `sherlock.txt`
  (`exists size=575 lines=17`); `result.json` holds 17 findings (16 claimed URLs plus the
  seed); its egress log reads `total 439 statuses {200: 435, 502: 3, 308: 1}` with no
  rate-limiter refusals. The report's claims grew from 13 to 32.
- **`ProxySession.start()` readiness holds live.** `social_username`'s egress log — empty in
  run `39135219248` — now reads `total=2 hosts={'mastodon.social': 1, 'api.github.com': 1}`
  with `statuses = {200: 2}`. Both upstream sources still return nothing usable (octosuite:
  `HTTP 403; stopped without redirect or retry` from inside the tunnel — GitHub's
  unauthenticated limit; masto: no finding); that is an upstream result, not a wiring
  failure.
- **`AUDIT.jsonl` records the fixed invocations**: `sherlock ["--no-color", "--txt",
  "--output", "/work/sherlock.txt", "--timeout", "60", "frost2233"]` and `maigret
  ["frost2233", "--no-autoupdate", "--no-progressbar", "--no-color", "--dns-resolver",
  "threaded", "--json", "ndjson", "--folderoutput", "/work/results"]` — no `--proxy`.
- Coverage change, recorded honestly: the dispatch envelope was raised from
  `egress_rate=20, egress_burst=100` to `100/500`, because under the old envelope our own
  limiter refused roughly half of each one-shot sweep (176 refusals for sherlock alone in
  run `39135219248`); with the envelope raised, neither sweep contains a single refusal and
  the detection counts above were obtained without one.
- Outcome: 16 sherlock sites plus 19 maigret accounts (24 distinct URL claims after
  canonicalization, including one exact-canonical merge), `entity_count` 32, `edge_count`
  43, `resolution_candidate_count` 3 — all candidates, nothing auto-merged on fuzzy
  similarity alone — plus `report.pdf`, `report.stix2.json` and `graph.graphml`. Findings
  are same-username **candidates**, not proof of ownership: several platforms present
  different display names, which is exactly the caveat the report carries. `instaloader`
  still ends on Instagram's side (`429 Too Many Requests`); `reddit-api`, `youtube-api` and
  `leak_checkers` remain key-gated skips (Gate 3).

## 2026-10-18 — Live-path repair round 3 after run `39135219248`: single-hop proxying, proxy readiness, sherlock results file, CI-verified

- **`maigret` tunnelled to the proxy through the proxy.** 455 of the 757 entries
  in its `EGRESS.jsonl` address the proxy's own container, e.g.
  `{"adapter":"maigret","bytes":272,"host":"aletheia-egress-maigret","method":"CONNECT","path":"","purpose_id":"unspecified","request_id":"97862c6f3d4341aa85d8c9d2394e8a98","status":200,"timestamp":"2026-10-18T14:30:03.385124+00:00"}`
  — 235 are the rate limiter refusing the outer connect (`status 429`,
  `bytes 0`), 164 relayed only 248–395 bytes each (a single TLS ClientHello's
  shape), and 56 relayed larger payloads (max 996 557 bytes). Its stdout
  records `Too many errors of type "Proxy" (46.17%)`. Root cause: maigret
  0.6.6's `SimpleAiohttpChecker` builds an `aiohttp_socks.ProxyConnector` from
  `--proxy` and opens the session with `trust_env=True`; with
  `HTTP_PROXY`/`HTTPS_PROXY` also set, aiohttp asks that connector to tunnel to
  the environment proxy address, so the proxy dials itself.
  `MaigretAdapter.build_command` no longer passes `--proxy`: the environment is
  the single transport channel, honoured by both of maigret's transports
  (reproduced locally against `docker/egress_proxy/proxy.py`: with the flag the
  connector logs `CONNECT 127.0.0.1` even with the rate limit wide open,
  env-only logs `CONNECT example.com`, and `curl_cffi` env-only also logs
  `CONNECT example.com`). This supersedes the `--proxy` wiring of the previous
  entry.
- **`ProxySession.start()` did not wait for the proxy to accept connections.**
  The `social_username` result records `masto: URLError: <urlopen error
  [Errno 111] Connection refused>` and the same for `octosuite`: the adapter
  ran in the window between `docker run -d` returning and the proxy process
  binding port 8888, so both sources failed instantly and the egress log was
  left empty. `start()` now runs a bounded `docker exec` loopback-connect probe
  (`ProxySession.probe_command`) and fails the session loudly if the proxy
  never accepts. The probe was executed locally: rc=0 in 0.09 s against a live
  proxy, rc=1 after 15.06 s with a clear stderr against a dead port. An empty
  probe connection leaves no log entry (the proxy discards it via
  `_read_head`'s `IncompleteReadError`), so the scenario's exact-count
  assertions (`entries=1`, `log_entries=7`) stay exact.
- **`sherlock` never wrote the file its parser reads.** Its stdout lists nine
  claimed results and `[*] Search completed with 9 results`, while
  `result.json` contains only the seed finding: sherlock 0.16.2 computes the
  file named by `--output` and gates the actual write behind `--txt`
  (`if args.output_txt:` in `sherlock_project/sherlock.py`), so nine live
  findings were silently dropped from the graph and report — the parser
  fixture writes `sherlock.txt` itself, so CI could not see the missing export
  flag. `build_command` now passes `--txt` next to `--output`.
- Local consistency: 721 passed + 65 skipped = 786 CI passed (run `39139781693`;
  scenario 9/9 with the readiness probe exercised under real Docker, capture
  60/60, storage 6/6, parser 49/49). Three new tests; the `--proxy` command
  assertion of the previous entry now asserts the opposite, because the flag
  was the defect; no test was skipped, deleted, or weakened.

## 2026-10-18 — Live-path repair after run `39125383530`: CONNECT tunnel, env proxies, maigret startup, CI-verified
- **The CONNECT tunnel pumped one direction only.** Every tunneled request in
  run `39125383530` failed while the proxy logged `200`. The artifact shows
  sherlock's CONNECT entries recording `"bytes": 0` (`api.github.com`,
  `data.sherlockproject.xyz`), instaloader's recording `"bytes": 7` — the
  length of a TLS alert — three times, and instaloader's stderr ending in
  `SSLError(SSLError(1, '[SSL] unknown error (_ssl.c:1032)'))`: `_tunnel`
  relayed the upstream reply to the client but never the client's bytes to the
  upstream, so the TLS ClientHello never left the proxy. `_pump_bidirectional`
  now runs both pumps concurrently, sends one EOF per direction, cancels the
  sibling when a side breaks, and its count of both directions is what lands
  in `EGRESS.jsonl`; the egress contract's `bytes` row documents the CONNECT
  semantics.
- **`social_username` ignored the environment proxies.** Its runner built the
  urllib opener with an explicitly empty `ProxyHandler({})`, so both sub-sources
  failed with `masto: URLError: <urlopen error [Errno -3] Temporary failure in
  name resolution>` and `octosuite: ...` while the proxy log stayed empty for
  that adapter. The opener now installs a default `ProxyHandler()` (which reads
  `HTTP_PROXY`/`HTTPS_PROXY`) alongside the no-redirect handler; the tests that
  had pinned the empty map now assert the environment-proxy handler and that
  requests go through a stub proxy.
- **`maigret` crashed before its first check under `--read-only`:** the
  database autoupdate called `os.makedirs('/root/.maigret')` and the
  container's stderr ended
  `OSError: [Errno 30] Read-only file system: '/root/.maigret'`.
  `MaigretAdapter.build_command` now passes `--no-autoupdate` (the flag skips
  the home-directory state entirely), plus `--no-progressbar`, `--no-color`,
  `--dns-resolver threaded`, `--json ndjson` and `--folderoutput /work/results`,
  and `--proxy` when the request carries one.
- **The scenario pins the tunnel defect class:** `ci/egress_scenario.py`
  generates a throwaway `-subj /CN=uplink-origin` certificate, serves a TLS
  origin beside the plain origin on the uplink network and asserts a new
  `phase12-egress-uplink-https` check (the origin body through the CONNECT
  tunnel plus a logged CONNECT entry with `bytes > 0`). Two local unit tests
  cover `_pump_bidirectional` and the CONNECT handler's relay + byte logging.
- **Two CI-only defects found while verifying the repair** (cancelled run
  `39128092472`, both in the new code's CI path): the new pump test used
  blocking `socket.socketpair()` ends with `loop.sock_recv()`, which deadlocks
  the Linux selector loop — the job sat at that test for 40+ minutes while
  Windows' proactor loop masks the defect; the ends are now non-blocking. The
  TLS origin runs as uid 10001 while OpenSSL writes private keys mode 0600, so
  the origin could not read `/origin/key.pem` and never listened (the run's
  `EGRESS.jsonl`: 24 origin requests all `status` 502 with `bytes` 0); the
  scenario now chmods both throwaway files 0644. The CONNECT test also closes
  its client writer and bounds `wait_closed()` so a future mid-test failure
  fails fast instead of stalling CI.
- **Verified** by Docker Verification run `39133692280` on commit
  `692e4181596be816d092a8bf9c1ed12b17594848`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39133692280).
  Lines copied from the downloaded artifact:
  `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `783 passed, 1 warning in 48.68s`;
  `DOCKER CAPTURE: PASS — 60/60 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`.
  `pytest-summary.json`: `junit_total` 783, `skipped_in_ci` `[]`, `ok` `true`.
  `results.json`: 60 entries, 0 nonzero return codes.
  `storage-conformance.json`: `configured`/`passing` = file, postgres, neo4j,
  elasticsearch, minio, redis; `unconfigured` `[]`; `required_all` `true`.
  `egress-scenario.json`: all 9 checks ok, including
  `phase12-egress-forward` = `proxy forwarded to the local origin`,
  `phase12-egress-uplink-https` = `tls through the CONNECT tunnel ok; bytes=2804`
  and `phase15-egress-previously-unwired-adapter` =
  `crtsh rc=1 new CONNECT crt.sh entries=1 status=200`.
  `EGRESS.jsonl` (scenario): 7 entries, every one `status` 200 with nonzero
  `bytes` — the origin and uplink-origin GETs (25 each) and the CONNECT
  tunnels `uplink-origin` 2804, `api2.marginalia-search.com` 5695,
  `index.commoncrawl.org` 5335, `crt.sh` 8763.
  Local consistency: 718 passed + 65 skipped = 783 CI passed. 6 new tests; no
  test was skipped, deleted, or weakened.

## 2026-10-18 — Live-path repair after run `39120709419`: docker argv, entrypoint-args commands, honest reporting, CI-verified
- **`run_docker` never told Docker what to run.** Run `39120709419` was the
  first live invocation of the container path in the project's history; every
  adapter "completed" in seconds while its `result.json` recorded exit code 1
  and `docker: 'docker run' requires at least 1 argument` on stderr, and
  `report.json` still listed them as ran. `execution.run_docker` now appends
  `[image, *command]`, and `_adapter_summary` reads each invocation's
  `result.json` (`ok`/`succeeded` -> ran, `partial`, `failed`/`error`, missing
  -> unknown) with `exit_code` plus the last non-empty stderr line.
- **29 of 49 adapters repeated their image's ENTRYPOINT** inside
  `build_command` (full entrypoint, `runner.py` script, or bare Go binary), so
  even a correct argv would have run the wrong program. Commands are now
  arguments-only; `deepface`/`insightface` additionally passed a host workspace
  path into the container and now pass `/work/input.<ext>`. New invariant test
  `tests/test_adapter_invocation_consistency.py` (49 parametrized cases) builds
  every adapter's command with a sample seed and checks it against the
  ENTRYPOINT parsed from the Dockerfile `docker/build.sh` builds the image from
  (basename-aware; rejects host workspace paths in commands).
- **Two honesty defects found in the same artifact:** `reddit-api` fabricated a
  profile URL from the seed when its payload was empty
  (`raw_evidence_sha256` was the SHA-256 of the empty string), and `sherlock`
  marked its seed claim `searched` ("Collector searched public sites") even
  when no container had run. Claiming an account now requires the payload to
  carry the username; the sherlock attribute and note follow the evidence.
  `reddit-api`/`youtube-api` emit credential-skip findings on exit code 5 so a
  key-gated adapter appears in `manifest["skipped"]` and in the report with the
  runner's own reason instead of an ambiguous gap.
- **`ProxySession` dual-homes the proxy** (`uplink`, default `bridge`): the
  `--internal` network has no route out, so a single-homed proxy could reach no
  upstream at all; the bind-mounted log dir is now made world-writable for the
  proxy's unprivileged uid. `ci/egress_scenario.py` runs the real
  `ProxySession` lifecycle and added `phase12-egress-uplink-forward` /
  `phase12-egress-uplink-isolated`; the crtsh check asserts exactly one new
  CONNECT entry rather than requiring the runner to fail closed.
- **Verified** by Docker Verification run `39123918529` on commit
  `4583d38a0db45756fccfe978087e0abec343bcb8`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39123918529).
  Lines copied from the downloaded artifact:
  `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `777 passed, 1 warning in 158.97s (0:02:38)`;
  `DOCKER CAPTURE: PASS — 59/59 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`.
  `pytest-summary.json`: `junit_total` 777, `skipped_in_ci` `[]`, `ok` `true`.
  `results.json`: 59 entries, 0 nonzero return codes.
  `storage-conformance.json`: `configured` = file, postgres, neo4j,
  elasticsearch, minio, redis; `unconfigured` `[]`; `required_all` `true`.
  `egress-scenario.json`: all 8 checks ok, including
  `phase12-egress-uplink-forward` = `proxy forwarded to the uplink-network origin`,
  `phase12-egress-uplink-isolated` = `direct-to-uplink='UNREACHABLE URLError'`, and
  `phase15-egress-previously-unwired-adapter` = `crtsh rc=1 new CONNECT crt.sh entries=1 status=200`.
  Local consistency: 714 passed + 63 skipped = 777 CI passed. 59 new tests; no
  test was skipped, deleted, or weakened.

## 2026-10-18 — Phase 16: multi-seed investigations, context filters, jurisdiction warnings, adapter-run reporting, Tier 5 rejection, CI-verified
- **Multi-seed runs implemented** (`f0352a4`): `create_run` accepts one seed
  (unchanged single-seed behavior) or a sequence; every matching adapter is
  scheduled once per supported seed (`manifest["pending_seeds"]`), each seed
  expands in its own workspace (`adapter@seedN`, 1-based) and evidence tree
  (`Provenance.seed_index`), and the resolver intersects the trees — an entity
  corroborated by two or more trees gets a bounded boost
  (`score * (1 + 0.05 * (trees - 1))`, capped at 1.0) that never creates a
  candidate (the raw threshold is applied first) and never feeds the Phase 13
  calibrator; the candidate explanation records `cross_seed_trees` and
  `cross_seed_boost=<raw>-><boosted>`. `docs/MULTI_SEED.md` records the
  semantics and limits. Single-seed runs keep their prior artifact shape:
  provenance stays untagged, workspace names and `tools_invoked` labels are
  unchanged, and `pending_seeds` is the only manifest addition; legacy manifests
  without it remain resumable.
- **Context filters** (country, age min/max, language, timezone) are stored in
  the manifest, carried on every `AdapterRunRequest`, and enforced at
  resolution: only positive mismatches flip a candidate to `filtered_out` with a
  `context_filter_mismatch=...` explanation, and an entity that records nothing
  for a filtered attribute is never excluded. No ISO-3166 dataset is bundled and
  no adapter consumes the filters as query hints yet.
- **Informational jurisdiction warnings** (`docs/JURISDICTION_WARNINGS.md`):
  strong-privacy jurisdiction, minor, health-data, and protected-class
  heuristics over seeds and entity attributes, deduplicated, recorded as
  `jurisdiction_warning` audit events (before `phase2_finalize`, same hash
  chain), in `report.json`, and in the PDF. They never gate a run and are not a
  legal determination.
- **Adapter-run reporting:** `resume` persists adapter-recorded sub-source skips
  (missing keys, retired endpoints, paid-only APIs) to `manifest["skipped"]`;
  `report.json`/`report.pdf` list every matching adapter with its outcome and
  each skip reason, and mark failed and still-pending adapters. `resume` also
  records the optional lawful-basis declaration in the audit trail on every run;
  an empty declaration does not stop a run.
- **Tier metadata is enforced:** `PROJECT_MANIFEST.json` validation requires
  `legal_tier` (integer 1..5), `enabled_by_default`, and `batch_grouping` for
  every adapter entry, with a non-empty `disabled_reason` when
  `enabled_by_default` is false (all 49 adapter entries pass); the registry
  refuses to construct an adapter whose entry declares `legal_tier=5` (Tier 5 is
  the project floor). Tiers 1–4 build.
- **CLI/API/MCP** accept repeatable seeds and context filters: `--seed` may be
  repeated plus `--filter-country|--filter-age-min|--filter-age-max|--filter-language|--filter-timezone`;
  the HTTP API and the MCP `investigate` tool take `seeds` + `context_filters`.
- **Verified** by Docker Verification run `39116485331` on commit
  `f0352a4f752934d8d5ae3bd320c659e4a8a475e3`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39116485331).
  Lines copied from the downloaded artifact:
  `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `714 passed, 1 warning in 29.49s`;
  `DOCKER CAPTURE: PASS — 57/57 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`.
  `pytest-summary.json`: `junit_total` 714, `skipped_in_ci` `[]`, `ok` `true`.
  `results.json`: 57 entries, 0 nonzero return codes.
  `storage-conformance.json`: `configured` = file, postgres, neo4j,
  elasticsearch, minio, redis; `unconfigured` `[]`; `required_all` `true`.
  `egress-scenario.json`: all 6 checks ok, including
  `phase15-egress-policy-covers-registry` = `adapters=49 network_required=44 wired=44`
  and `phase15-egress-previously-unwired-adapter` = `crtsh rc=1 new CONNECT crt.sh entries=1 status=502`.
  Local consistency: 653 passed + 61 skipped = 714 CI passed. 36 new tests; no
  test was skipped, deleted, or weakened.

## 2026-10-18 — Phase 15: every network-requiring adapter routes egress through the proxy, CI-verified
- **Coverage is a policy, not an allowlist.** `EGRESS_WIRED_ADAPTERS` (the
  `search_engines` / `ssl_tls` / `ip_intelligence` subset from Phase 12) is replaced by
  `egress.is_wired(name, network_required=descriptor.network_required)`: an adapter's egress
  goes through the proxy whenever its descriptor declares `network_required=True`.
  `EGRESS_EXEMPT_ADAPTERS` is the (empty) list of documented exceptions. Measured against the
  registry: 49 adapters, 44 declare `network_required=True`, 44 wired.
- **The proxy is now the default path.** `Orchestrator.resume` wires by default; previously it
  required `wire_egress=True`, which neither the CLI nor the MCP server ever passed, so the
  proxy was effectively test-only in production paths. Offline replays pass
  `wire_egress=False`, and `aletheia investigate` / `aletheia resume` gained
  `--no-egress-proxy` as the explicit opt-out.
- **Coverage is checked, not claimed.** `tests/test_egress_wiring.py` walks all 49 adapters and
  asserts the policy matches their descriptors. `ci/egress_scenario.py` adds
  `phase15-egress-policy-covers-registry` and a real-container
  `phase15-egress-previously-unwired-adapter` check: `crtsh`, never in the Phase 12 allowlist,
  runs on an `--internal` network and its HTTPS attempt is logged by the proxy
  (`crtsh rc=1 crt.sh log entries=1` — fail-closed, as it must be). Two Docker integration
  tests assert those checks.
- Honest limits recorded in `docs/EGRESS_PROXY_CONTRACT.md`: the proxied path is proven end to
  end for four adapters; an adapter whose client ignores `HTTP_PROXY` / `HTTPS_PROXY` fails
  closed rather than egressing unproxied, but that failure mode is not separately demonstrated
  per adapter, and some third-party CLI adapters may use their own resolvers.
- Verified by Docker Verification run `39084899431` on commit
  `9f1c09288961d5175ff6c2d68b8b6f7f307074d7`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39084899431). Lines copied
  from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `678 passed, 1 warning in 36.14s`; `DOCKER CAPTURE: PASS — 57/57 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`. `pytest-summary.json`: `junit_total` 678,
  `skipped_in_ci` `[]`, `ok` `true`. `results.json`: 57 entries, 0 nonzero return codes, both
  `phase15-*` entries present. Local consistency: 617 passed + 61 skipped = 678 CI passed. No
  test was skipped, deleted, or weakened.
- **A defect caught before it shipped: the evidence was computed but not reported.** Run
  `39083768809` executed all 677 cases with 0 skipped and failed one test because the scenario
  appended the policy check and then `main()` overwrote `summary["checks"]` with the dict
  returned by `_run_checks`. The list is now assembled in one place, and a unit test pins the
  check's name and result.

- **Evidence hardened (run 39087297928).** The crtsh scenario check counts CONNECT crt.sh
  entries before and after the container run and requires exactly one new one, instead
  of counting entries after the run alone: the scenario's single proxy tags every
  container `search_engines`, so an after-only count could have matched a
  `search_engines` entry and passed without the crtsh container's request having gone
  through the proxy. Artifact detail: `phase15-egress-previously-unwired-adapter` =
  `crtsh rc=1 new CONNECT crt.sh entries=1 status=502`. Same run: `678 passed, 1 warning in 38.12s`; `DOCKER CAPTURE: PASS — 57/57 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`; `pytest-summary.json` `junit_total` 678,
  `skipped_in_ci` `[]`, `ok` `true`;
  `results.json` 57 entries, 0 nonzero. Local consistency:
  617 passed + 61 skipped = 678 CI passed.

## 2026-10-18 — Phase 14: storage backends behind one conformance contract, CI-verified against real services
- **One contract, six backends.** `app/aletheia/storage/base.py` defines `StorageBackend`
  (graph snapshots + run manifests), implemented by `file`, `postgres`, `neo4j`,
  `elasticsearch`, `minio` and `redis`. Backends store whole JSON documents so a snapshot
  round-trips byte-for-byte; Neo4j *additionally* materialises `(:AletheiaEntity)` nodes and
  `[:RELATED]` relationships scoped by `run_id`, with `verify_materialised()` as the
  conformance hook that proves it.
- **Migration runner.** `MigrationRunner` applies ordered migrations once, records
  `(version, name, checksum, applied_at)`, and raises `MigrationError` on checksum or name
  drift. `prepare_migrations()` runs before the runner reads that log, because the log table
  cannot be created by a migration the runner has not yet read.
- **Shared conformance contract.** `app/aletheia/storage/conformance.py` is used by both the
  pytest suite and the CI evidence script so they cannot drift; a `BrokenBackend` negative
  control proves the contract can fail. The five service tests skip *only* when their
  environment variable is unset, so in CI a broken service is a failure, never a skip.
- **CLI.** `aletheia storage health|migrate|sync`; `sync` applies the backend's migrations
  first, so mirroring a run into a fresh database works in one step.
- Honest limits (documented in `docs/STORAGE_BACKENDS.md`): the hash-chained `AUDIT.jsonl`
  stays on local disk (its tamper-evidence depends on atomic `fsync` appends), the
  orchestrator still writes through `FileGraphStore` by default (networked backends are
  populated via `storage sync`), and Redis is a fast-path cache, not a system of record.
- **MinIO substitution, disclosed:** `minio/minio` returns 404 on Docker Hub (deleted
  2026-09) and `quay.io/minio/minio` refuses anonymous pulls, so CI verifies the S3 code path
  (`minio-py`) against `adobe/s3mock:5.2.3`, a real S3-protocol server, rather than against a
  MinIO server.
- Verified by Docker Verification run `39081533916` on commit
  `e9bfdda953622c4eda69f342f294a09e23d0b73b`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39081533916). Lines copied
  from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `672 passed, 1 warning in 36.02s`; `DOCKER CAPTURE: PASS — 55/55 cases captured`;
  `STORAGE CONFORMANCE: PASS — 6/6 backends conform`. `pytest-summary.json`: `junit_total` 672,
  `skipped_in_ci` `[]`, `ok` `true`. `storage-conformance.json`: `passing` = file, postgres,
  neo4j, elasticsearch, minio, redis, `unconfigured` `[]`. `results.json`: 55 entries, 0
  nonzero return codes. Local consistency: 613 passed + 59 skipped = 672 CI passed. No test was
  skipped, deleted, or weakened; no `parser_test_exempt`.
- **Two defects found only by CI** (runs `39078543221` → `39079850431` → `39081533916`):
  PostgreSQL health always reported `ok: false` because pg8000 appends every row as a Python
  `list`, so `[[1]] != [(1,)]`; and `migrate` failed with `relation
  "aletheia_schema_migrations" does not exist` because the runner read that table before
  migration 1 created it. Both are fixed and pinned by tests that need no server. A third
  failure was a test asserting the developer machine's environment (every backend variable
  unset), which fails in CI where they are all set; it is now environment-independent.
- **CI now proves execution, not just success.** `ci/pytest_summary.py` cross-checks the JUnit
  XML against the pytest console summary and fails the job if anything skipped;
  `ci/storage_conformance.py --require-all` fails when a backend is unconfigured. Both exist
  because run `39078543221` reported `STORAGE CONFORMANCE: PASS` while no storage service had
  started at all. The workflow also frees the runner's unused SDKs before building (13 GB → 35 GB
  free; the earlier run died with `no space left on device` while pulling the Elasticsearch
  image) and captures the service logs as evidence.

## 2026-10-17 — Phase 13: score calibration (Platt scaling + isotonic regression), CI-verified
- **Calibration.** `app/aletheia/core/calibration.py` — new. `PlattScaling` fits
  `sigmoid(slope * score + intercept)` by Newton-Raphson on Platt-smoothed targets;
  `IsotonicRegression` fits a monotone step function by pool-adjacent-violators. Both are pure
  standard library. `Calibrator.trained` stays `False` below `MIN_LABELED_PAIRS = 8` pairs or
  when a class is missing, so an untrained model is never presented as a probability.
- **Resolver integration.** `app/aletheia/phase2/resolution.py` — `EntityResolver` takes an
  optional `Calibrator` and reports `calibrated` / `calibrated_probability` per
  `SAME_AS_CANDIDATE` edge; without a trained calibrator they are `false` / `null` and the raw
  similarity composite is preserved.
- `tests/test_calibration.py` — 18 tests; `tests/fixtures/calibration_pairs.json` — 80
  **synthetic** labelled pairs (deterministically generated, seed 20261017), explicitly not
  real investigation data. `docs/ADAPTER_CONTRACT.md` gained a "Calibrated vs uncalibrated
  scores" section.
- Honest limitation: the synthetic fixture demonstrates the mechanism, not a
  production-calibrated model; real calibration is deferred until labelled pairs from
  authorised investigations exist.
- Verified by Docker Verification run `38972618582` on commit
  `f1a9a840c3dc9e0e16caefb640b2c934b2b6edeb`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38972618582). Lines copied
  from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `634 passed, 1 warning in 30.13s`; `DOCKER CAPTURE: PASS — 55/55 cases captured`. `results.json`:
  55 entries, 0 nonzero return codes. Local consistency: 580 passed + 54 Docker skips = 634 CI
  passed. No test was skipped, deleted, or weakened; no `parser_test_exempt`.

## 2026-10-17 — Phase 12: egress proxy wired into a representative subset, CI-verified
- **Wiring.** `egress.ProxySession` creates a fresh `docker network create --internal`
  network (no default egress — the proxy is the only route out) and starts the detached
  egress proxy on it with no published host port, so it is addressed by container name.
  `EgressProxy.run_command` gained `detached`/`publish_port`; container names are made
  DNS-safe (underscores become hyphens). `execution.run_docker(..., network_name=...)` joins
  the named network instead of `bridge`/`none`, and `AdapterRunRequest.network_name` carries
  it from the orchestrator. `orchestrator.resume(..., wire_egress=True)` starts a session per
  wired adapter and appends the proxy's request log to the run's Phase 10 chain as
  `egress_request` events.
- **Representative subset.** `EGRESS_WIRED_ADAPTERS = (search_engines, ssl_tls,
  ip_intelligence)`. The other 46 adapters are deliberately **not** wired; full coverage is
  deferred. "Wire the proxy into the adapter Dockerfiles" is therefore only partially met.
- `ci/egress_scenario.py` — new end-to-end scenario under real Docker: a local origin plus the
  adapter image as the client on an `--internal` network, proving the forwarded 200, the real
  `search_engines` runner egressing through the proxy (`rc=0`), a valid hash-chain append of
  four `egress_request` events, and the fail-closed property (no direct internet; no path once
  the proxy is stopped). `ci/capture_docker_integration.py` records its four
  `phase12-egress-*` checks.
- `tests/test_egress_wiring.py` (11 unit tests) and three new `tests/test_docker_integration.py`
  cases; `docs/EGRESS_PROXY_CONTRACT.md` gained a "Wiring pattern" section. The CI workflow
  step name that hardcoded "45" Docker integration cases was corrected to carry no count.
- Verified by Docker Verification run `38970577087` on commit
  `ccd5a4b1b9bde0532936911e06685f4f2518314d`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38970577087). Lines copied
  from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`;
  `616 passed, 1 warning in 31.17s`; `DOCKER CAPTURE: PASS — 55/55 cases captured`. `results.json`:
  55 entries, 0 nonzero return codes. Local consistency: 562 passed + 54 Docker skips = 616 CI
  passed. No test was skipped, deleted, or weakened.

## 2026-10-17 — Phase 11: egress proxy (standalone component) implemented and CI-verified
- **Egress proxy, standalone.** `app/aletheia/core/egress.py` is the control-plane side:
  JSONL schema parsing (`EgressLogEntry`, `parse_log_line`, `read_log`), a per-adapter
  token-bucket rate limiter with optional atomic JSON persistence (`TokenBucket`,
  `AdapterRateLimiter`), a single kill switch (`KillSwitch`), the container/argv and adapter
  proxy-environment builder (`EgressProxy`), and `append_log_to_chain`, which writes each
  proxied request into the run's hash-chained audit log from Phase 10.
- `docker/egress_proxy/proxy.py` is a standard-library `asyncio` forward proxy (image
  `aletheia/egress-proxy:v1`). Plain HTTP is forwarded from an absolute-form target; HTTPS
  `CONNECT` is tunnelled. The kill switch (403) and the token bucket (429) are applied
  before any upstream connection opens; an upstream connect failure logs 502. `--health`
  prints exactly `ok` and opens no socket, so the container smoke runs under `--network none`.
  **Recorded deviation:** it is not literally ASGI, because ASGI cannot carry `CONNECT`
  tunnels; the `docs/EGRESS_PROXY_CONTRACT.md` control-plane contract is unchanged.
- `docs/EGRESS_PROXY_CONTRACT.md` created (it was missing from the repository).
- Scope: this is a **standalone** component. It is deliberately **not** wired into the
  adapter Dockerfiles yet, so no adapter traffic is forced through it. That wiring is a
  later session.
- Verified by Docker Verification run `38961709929` on commit
  `02ee8879330d5195d48f3a7d47b3c0aa28080422`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38961709929). Lines copied
  from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have parser
  coverage`; `602 passed, 1 warning in 20.79s`; `DOCKER CAPTURE: PASS — 51/51 cases captured`.
  `results.json`: 51 entries, 0 nonzero return codes, the `phase11-egress-proxy` case
  (`docker run --rm --network none aletheia/egress-proxy:v1 --health`) returned 0, SHA-256
  `DEED8B3B1C8F62BD77D0B835666672AA5504076211525C161D4EBA9B2C3EA1CF`. The image built as
  `sha256:f5af6b1f42d9e8cdb5a637bef81534496aa194fe422e18e1187f61ec4ddd12a0`; the Dockerfile
  SHA-256 is `eb7ce40f08eee36733d045d726bee8b6532ee4d196c4dccb2e42bc2ac8e761d1`, matching the
  local file. Local consistency: 551 passed + 51 Docker skips = 602 CI passed. Manifest entry
  `egress_proxy` flipped to `verified-fixture` in commit `255dc6d`; no test was skipped,
  deleted, or weakened.

## 2026-10-16 — Phase 10: hash-chained audit log implemented and CI-verified
- **Audit chain.** Each run's `AUDIT.jsonl` is now a SHA-256 hash chain
  (`app/aletheia/core/chain.py`). Every entry carries a one-based `seq`, the previous
  entry's hash as `prev_hash` (64 zeroes for the genesis entry), and its own `hash`
  (SHA-256 of the canonical UTF-8 JSON with `hash` removed, keys sorted, compact
  separators). `append()` refuses to extend an invalid chain, a chain whose tip disagrees
  with the run `MANIFEST.json` anchor, or a run whose `checkpoint_hash` is invalid.
  `AuditLogger.log()` routes every event through the chain; the orchestrator and
  `Phase2Service` verify the chain before publishing a tip or mutating a run; and the CLI
  adds `aletheia verify-chain <RUN_ID>`.
- **Honest limitation, stated in the README and `docs/ADAPTER_CONTRACT.md`:** the chain is
  tamper-EVIDENT relative to a preserved manifest anchor. It is not a digital signature,
  it does not authenticate the manifest against an actor able to rewrite both files, and
  it is not a legal-admissibility guarantee.
- Verified by Docker Verification run `38958865080` on commit
  `503710890140d573451ba5363a10655f979e2ed4`
  (https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38958865080). Lines
  copied from the downloaded artifact: `PARSER PREFLIGHT: PASS — 49/49 adapters have
  parser coverage`; `570 passed, 1 warning in 23.03s`; `DOCKER CAPTURE: PASS — 50/50 cases
  captured`. `results.json`: 50 entries, 0 nonzero return codes, SHA-256
  `DA17BD0DF2B83FA6C771ED3B76F45EC42BBF271A3E04A5F186CF5FCAF5C03460`. Local consistency:
  520 passed + 50 Docker skips = 570 CI passed.
- Tamper-detection tests cover an edited middle entry, a removed final entry, a stale
  manifest anchor that must not be advanced, and a tampered `checkpoint_hash` that must not
  be repaired by an append. No test was skipped, deleted, or weakened.

## 2026-10-17— count-drift fix, code_search and search_engines
- **Count-drift fix.** tests/test_ssl_tls_adapter.py and tests/test_email_auth_adapter.py now assert `set(registry)` equals the set of adapters PROJECT_MANIFEST.json declares as Docker-invoked, and tests/test_phase3_manifest.py asserts the run pending set equals the live registry DOMAIN-capable set. Both are derived and strictly stronger than the literals they replaced, and both were proved to still fail when the source of truth is tampered with. A new adapter no longer requires editing any other test file. The phase3/4/5 adapter tests were deliberately left alone because they assert against frozen phase-specific registries. Verified by run `38807150831` on `4c2b38f`: `PARSER PREFLIGHT: PASS — 42/42 adapters have parser coverage`; `455 passed, 1 warning in 21.03s`; `DOCKER CAPTURE: PASS — 43/43 cases captured`.
- **code_search** (1 sub-source, 2 drops). Implemented `debian-code-search`, whose contract came from the project own OpenAPI specification (`https://codesearch.debian.net/api/v1`, `GET /search` with required `query` and optional `match_mode`, free key in the `x-dcs-apikey` header). Dropped `gitlab-search` (GitLab own documentation states every call to the Search API requires authentication, and a live probe of the blobs scope returned HTTP 401) and `publicwww` (its own authentication documentation states a paid plan is required, which standing rule 4 forbids). Verified by run `38811234205` on `f59458f`: `PARSER PREFLIGHT: PASS — 43/43 adapters have parser coverage`; `484 passed, 1 warning in 20.60s`; `DOCKER CAPTURE: PASS — 44/44 cases captured`.
- **search_engines** (2 sub-sources, 2 drops). Implemented `marginalia` (`https://api2.marginalia-search.com/search`, key in the `API-Key` header, documented public development key as fallback, content CC-BY-NC-SA 4.0 which is non-commercial) and `common-crawl-index` (`https://index.commoncrawl.org/`, no auth, crawl id pinned to `CC-MAIN-2026-39`, never a wildcard). Dropped `searxng` (a self-hosted metasearch engine whose JSON output is an instance-side setting, not a public API) and `google-custom-search` (Google own documentation states verbatim that the Custom Search JSON API is closed to new customers, with discontinuation on 2027-01-01). Verified by run `38813318506` on `316172b`: `PARSER PREFLIGHT: PASS — 44/44 adapters have parser coverage`; `518 passed, 1 warning in 15.38s`; `DOCKER CAPTURE: PASS — 45/45 cases captured`.
- The consistency check held for every part: local (passed + skipped) equalled CI passed exactly (412+43=455, 440+44=484, 473+45=518), which is the evidence that no test was skipped or deleted along the way.

## 2026-10-16— crypto_blockchain, patents_trademarks and email_auth implemented
- **crypto_blockchain** (6 sub-sources, 1 drop). `mempool-space`, `blockstream-esplora`, `blockchair`, `etherscan-v2`, `blockcypher` and `chainabuse`, each verified against its provider own documentation. `crypttrace` was **dropped**: its PyPI page and README document only a terminal CLI and a local web app, with no importable API. Verified by run `38797483163` on commit `9f53012`: `PARSER PREFLIGHT: PASS — 40/40 adapters have parser coverage`; `383 passed, 1 warning in 16.35s`; `DOCKER CAPTURE: PASS — 41/41 cases captured`.
- **patents_trademarks** (4 sub-sources, 3 drops). `uspto-open-data`, `uspto-patent-assignment`, `uspto-tsdr` and `epo-ops`. Dropped: `patentsview` (its documented API host `search.patentsview.org` no longer resolves; NXDOMAIN independently confirmed against the system resolver and 1.1.1.1), `google-patents-bigquery` (needs a GCP project, service-account credentials and a third-party client library) and `euipo-esearch-plus` (account plus sandbox and production approval). This composite absorbs EPO OPS and Google Patents from the plan separate `research_discovery` row. Verified by run `38801355462` on commit `0ae35e4`: `PARSER PREFLIGHT: PASS — 41/41 adapters have parser coverage`; `422 passed, 1 warning in 19.09s`; `DOCKER CAPTURE: PASS — 42/42 cases captured`.
- **email_auth** (2 sub-sources, no drops). `scan-mx` (keyless, `GET https://api.scan.mx/v1/check?domain=<domain>`, documented limit not published) and `checkdmarc` (Apache-2.0 library called through its documented `checkdmarc.check_domains` entry point). The image pins `checkdmarc==6.0.4`, independently re-confirmed against the PyPI JSON API. Committed as `9b949c7`; CI verification was still in progress when this entry was written, so its manifest status remains `unverified-fixture`.
- Cross-check used for every composite: the local (passed + skipped) total equals the CI passed total, because CI runs the container smokes that skip without a local Docker CLI. crypto: 342 + 41 = 383. patents: 380 + 42 = 422.

## 2026-10-16— ssl_tls implemented and CI-verified after two diagnosed failures
- Five sub-sources implemented. `qualys-ssl-labs` is an HTTP API (`GET https://api.ssllabs.com/api/v4/analyze?host=`, free registration, mandatory `email` header, documented concurrency limits, no numeric quota published). `testssl`, `sslscan`, `certgraph` and `tlsx` are local CLI tools baked into `aletheia/ssl-tls:v1`; the runner invokes each with an argv list and never a shell string. `cipherscan` was **dropped** because it publishes no releases and no tags, so no pinned verifiable artefact exists, and its README documents a bundled prebuilt OpenSSL rather than a packaged one. It is reported once per run as `skipped` with that reason.
- **Two red runs, both diagnosed and fixed rather than retried.** Run `38669069783` failed at the image build with `E: Version '2.0.7-1' for 'sslscan' was not found`; both intended versions were confirmed present in bookworm via `sources.debian.org`, so the base image's apt sources simply do not resolve those exact versions. Commit `7b0ccbc` removed the exact apt pins, installs the packages unpinned and echoes the resolved versions into every build log with `dpkg-query -W`. Run `38789002369` then built successfully but failed one test: `query_testssl` and `query_sslscan` returned the artefact parse error (`FileNotFoundError`) instead of the tool exit code, because they evaluated `parse_error or _local_tool_error(...)` after the tool had already failed. The test had been passing locally only by accident, because the Windows temp directory name happened to contain the digit `1`. Commit `a7c394d` makes both functions check `code != 0` before reading the artefact, verified with a stubbed failing tool.
- Docker Verification run `38791430700` on commit `a7c394d` passed every step. Lines copied from the downloaded artifact: `PARSER PREFLIGHT: PASS — 39/39 adapters have parser coverage`; `343 passed, 1 warning in 24.95s`; `DOCKER CAPTURE: PASS — 40/40 cases captured`. `results.json`: 40 entries, 0 nonzero return codes, 40 stdout/stderr pairs, SHA-256 `5134BD59E5E6AAC2727088582414721A4308C01EF44E82A63221C1FD6B2964F6`; `phase9-ssl-tls` returned 0 with stdout `ok` under `--network none`.
- The `--health` inventory written to stderr proves the image really contains the tools: `/usr/bin/testssl`, `/go/bin/certgraph`, `/usr/bin/sslscan` and `/go/bin/tlsx` are each reported `usable: true` with `subprocesses_started: false` and `network_used: false`, alongside the `qualys-ssl-labs` HTTP source. This is the first composite image that installs real tools rather than only python, so this inventory is the evidence that its Dockerfile works.
- `EntityType.TLS_OBSERVATION` added. `tests/test_phase3_manifest.py` DOMAIN-seed pending inventory went 12 to 13 names for the new domain-capable adapter, which is a registry-count update, not a weakened assertion.

## 2026-10-15— academic_search implemented and CI-verified
- Six sub-sources implemented, each verified against its own vendor documentation before any code was written: `openalex` (`search`, 10 req/s without a key), `crossref` (`query.bibliographic`, optional polite `mailto`, rate limit not published), `semantic-scholar` (`query`, free `x-api-key`, documented shared 1000 req/s unauthenticated pool), `arxiv` (`search_query`, Atom XML, documented 3-second delay), `core` (`q`, no auth required, 100 requests/day unauthenticated) and `openaire` (`search`, 60 requests/hour unauthenticated).
- `unpaywall` was **dropped**, not omitted: its documented search endpoint is retired and returns `410 Gone`, and its only live endpoint is DOI-keyed, so no name-based request contract exists. The runner reports it once per run as `skipped` with that reason; the drop is recorded in the adapter, runner, `RATE_LIMITS.md`, fixture and manifest note.
- Docker Verification run `38658742093` on commit `9a24be885d88e740f078b6bdf5c62944f5002024` passed every step. Lines copied from the downloaded artifact: `PARSER PREFLIGHT: PASS — 38/38 adapters have parser coverage`; `292 passed, 1 warning in 15.83s`; `DOCKER CAPTURE: PASS — 39/39 cases captured`. `results.json`: 39 entries, 0 nonzero return codes, 39 stdout/stderr pairs, SHA-256 `1C91399BD3271A49AA69437E683921449EA625BCC290D29A416FC8EEF4946B60`; `phase9-academic-search` returned 0 with stdout `ok` under `--network none`.
- `EntityType.ACADEMIC_RECORD` added; no existing entity type covered publications. No `SeedType` member was added.

## 2026-10-15— corporate_financial_public_records: verification failed, adapter not built
- Endpoint verification was performed before any code was written, as instructed, and it failed. Four of the composite's five planned sub-sources (`fdic-bankfind`, `lda`, `usaspending`, `sam-gov`) already live in `government_records_us`. The fifth, FollowTheMoney, publishes **no request-parameter contract for name-based queries**: its official 80-page API PDF documents response tags only and contains zero occurrences of `api.followthemoney.org`, `APIKey`, `mode=` or `entity.php`; the only concrete documented request is the entity-ID endpoint `entity.php?eid=&APIKey=&mode=`.
- A second, independent blocker: OpenSecrets' own API page states verbatim *"As of April 15, 2025, our API offerings have been discontinued"* and now offers only a commercial route. FollowTheMoney (NIMSP) merged into OpenSecrets and its site is explicitly unmaintained, with state data current only through 2024. A paid-only source is barred by standing rule 4.
- Live probes recorded: `https://api.followthemoney.org/` returns `invalid mode` without a `mode` parameter, and `?mode=json` returns exactly `{"error":"Invalid API Key"}`, which confirms the base URL, the `APIKey` parameter and the `mode=json` mode. No rate limit is published anywhere. **No adapter, runner, Dockerfile, fixture, test, capture case, build target or manifest entry was created**; writing a name-search runner would have required inventing parameters.
- Recorded as an exclusion in `docs/NOT_INTEGRATED.md` with primary-source links and the raw verification commands, as Gate 7 in `GATES.md`, and as an implementation-status table in `docs/BATCHING_PLAN.md` covering the wider plan divergence: `ip_intelligence` absorbed three plan rows and `government_records_us` absorbed seven sub-sources the plan assigned to two other rows.

## 2026-10-15— sanctions_enforcement_watchlists implemented and CI-verified
- Implemented the composite scoped to the three sub-sources the plan assigns to it that were not already built: `uk-sanctions-list` (FCDO UK Sanctions List XML), `swiss-seco` (SECO whole-list XML, de-listed targets excluded) and `eu-consolidated-sanctions` (European Commission FSD XML 1.1 export). `finra-brokercheck`, `fed-enforcement` and `occ-enforcement` were deliberately left in `government_records_us` rather than duplicated; the manifest note and RATE_LIMITS.md record that overlap.
- All three endpoints were independently confirmed live: HTTP 200 with `text/xml` for the UK artefact (22,051,190 bytes) and the SECO download, and HTTP 200 with `application/xml` for the EU export (25,761,082 bytes). None of the three publishes a JSON search API, so the runner downloads the published bulk file per run and filters locally with the standard library; no third-party dependency was added and no rate-limit number was invented.
- Docker Verification run `38652416329` on commit `43bb9449d8667841a54bc5a5f6cf9b6f8cf362d8` passed every step. Lines copied from the downloaded artifact: `PARSER PREFLIGHT: PASS — 37/37 adapters have parser coverage`; `245 passed, 1 warning in 14.26s`; `DOCKER CAPTURE: PASS — 38/38 cases captured`. `results.json`: 38 entries, 0 nonzero return codes, 38 stdout/stderr pairs, SHA-256 `53253F65451032E061425E66F3FA37A83977B6C0450F161E80CB41D1D6FAFA02`; `phase9-sanctions-watchlists` returned 0 with stdout `ok` under `--network none`.
- `unverified-fixture` was added to `VERIFICATION_STATUSES` in `app/aletheia/core/project_manifest.py` as the pre-verification state for new adapters; no other assertion changed.

## 2026-10-15 — Pre-7f06d10 verification audit: fabrication isolated, citation gap closed
- **Audit scope.** All 10 successful Docker Verification runs on commits before `7f06d10` were re-examined from downloaded artifacts: `38270478612`, `38272314026`, `38273505822`, `38274729412`, `38275780719`, `38275780791`, `38290727897`, `38291743287`, `38292770527`, `38293763683`.
- **Result: no fabrication in any of them.** For every run, `ci-parser-preflight.txt`, the last line of `ci-artifacts/pytest-full.log`, the first line of `ci-artifacts/docker-integration/capture.log`, and `results.json` agree with each other: the capture count equals the number of `results.json` entries, every entry returns 0, and the stdout/stderr file counts equal the entry count. Every `capture.log` begins with a real `DOCKER CAPTURE: PASS — N/N cases captured` line. The fabrication in run `38323854024` was **isolated, not systematic**.
- **But a systematic citation gap existed.** 29 of the 36 `verified-fixture` adapters carried no run citation at all — their notes claimed only "Fixture parser coverage passes" while asserting `verified-fixture`. Every one of those 29 has a passing capture case in run `38293763683` (commit `d784850ed5d869393c63e180cfb05035c070513e`), so the evidence was real but undocumented. Commit `70f4828` added the run, the commit, the copied run-level evidence lines, and the per-adapter case name and return code to each of the 29 notes. **No `verification_status` was changed and no assertion was weakened.**
- The seven adapters that already cited a run were checked against their artifacts and all pass: `gravatar` (38179832021), `rdap` (38270478612), `ip_intelligence` (38303951248), `government_records_us` (38644757019), `corporate_registry` (38647832837) cite full evidence lines that match their artifacts exactly; `xposedornot` (38168341113) and `phoneinfoga` (38169632277) cite a run and their capture cases return 0 in it.
- `GATES.md` records the audit as cleared, with the standing rule that every `verified-fixture` adapter must cite a run whose artifact has been read (commit `7c6b19e`).

## 2026-10-14 — Fabricated capture evidence retracted; Docker verification restored
- **Integrity failure in run 38323854024.** The run was recorded as green with the evidence line `DOCKER CAPTURE: PASS — 35/35 phases captured`. That line appears **zero times** in the run's job log (1,107,792 bytes fetched with `gh run view --log`) and zero times in `ci-artifacts/docker-integration/capture.log`. The actual artifact ends with `=== Summary: 35 phases captured ===` and 18 of its 35 phases returned nonzero exit codes. The scratch script `update_manifest_verified.py` hard-coded the false line; it was never copied from an artifact. The script has been deleted and the adapter's `verified-fixture` status retracted to `unknown`.
- **What run 38323854024 actually did.** Commit `edcc433` replaced `ci/capture_docker_integration.py` with a version that runs `python docker/<dir>/runner.py` directly, never invokes `docker`, prints a PASS summary keyed on `len(phases)` rather than on success, and returns 0 unconditionally. It also printed a `PARSER PREFLIGHT` line that shadowed the real preflight line. The build, image-ID, and parser preflight steps of that run were genuine; the capture step was not.
- **Why the numbers moved.** Commit `edcc433` deleted the 35 `docker run` container smoke tests in `tests/test_docker_integration.py` and replaced them with 4 tests that shell out to a local runner over the live network. Pytest therefore went 152 → 146 (152 − 35 + 4 + 25 new government_records_us tests = 146 exactly) and CI runtime went 12.87s → 2.61s, because ~10s of the previous run was 35 container starts. The count never dropped to 146 because work was lost; it dropped because the container-smoke layer was removed.
- **Restored.** `ci/capture_docker_integration.py` runs `docker run --rm --network none` per case again, fails the step on any nonzero case, and gains `phase9-gov-records-us` (36 cases). `tests/test_docker_integration.py` restores the 35 deleted smoke tests and adds the gov-records-us health smoke (36 tests). `.github/workflows/docker-verification.yml` step renamed to 36 cases.
- **government_records_us parser tests were vacuous.** `test_parse_success`, `test_parse_skipped` and `test_parse_error` each built a payload, constructed the adapter, and asserted `adapter is not None`; none called `parse()`. The adapter could not satisfy the preflight's real rule, so commit `419004a` set `parser_test_exempt=True` with the reason "25 tests covering all 11 sub-sources and edge cases" — a reason that was not true. The three tests now call `adapter.parse()` and assert on the resulting findings and provenance hashes, two edge-case tests were added, the exemption was removed, and the preflight passes 35/35 on a real `@parser_test("government_records_us")` marker.
- **Manifest test un-weakened.** `test_verified_fixture_adapter_notes_name_existing_fixture_file` had been made case-insensitive to accommodate two notes written with a capital `Fixture file:`. The strict lowercase assertion is restored and the two notes were lowercased to match instead.
- Deleted ten scratch scripts (`add_manifest_entry.py`, `check_docker.py`, `check_manifest.py`, `fix_details.py`, `fix_manifest.py`, `fix_manifest2.py`, `fix_manifest_unverified.py`, `fixes.py`, `update_manifest.py`, `update_manifest2.py`) that had been committed to the repository root, and reverted the unused `pytest-mock` dev dependency.
- **Corrected run verified.** Docker Verification run `38644757019` on commit `e87777bf0ae873070c1aa9c49973a2aab0547a75` passed every step. Lines copied from the downloaded artifact: `PARSER PREFLIGHT: PASS — 35/35 adapters have parser coverage`; `180 passed, 1 warning in 17.00s`; `DOCKER CAPTURE: PASS — 36/36 cases captured`. `ci-artifacts/docker-integration/results.json` holds 36 entries with 0 nonzero return codes and 36 stdout/stderr pairs; SHA-256 `AF6DEC8F9F8E005F296A2254FB28C254F29F2AC5100C9E73CA1E2591687F970C`. Case `phase9-gov-records-us` returned 0 with stdout `ok` under `--network none`, and `phase7-core-import` is present again. Runtime returned to 17.00s from 2.61s, consistent with 36 container starts being restored.
- `government_records_us` was re-marked `verified-fixture` from that run in commit `58d48ee`, using only lines copied from the artifact. Local state on this workstation is 180 collected / 144 passed / 36 skipped, the skips being the container smokes (`docker` is not on PATH locally).

## 2026-10-12 — RDAP implementation and Florida framework
- Implemented the RDAP domain/IP adapter, isolated standard-library Docker runner, synthetic RFC-shaped fixture, parser tests, offline container health smoke, capture case, registry entry, and build target. The runner uses IANA bootstrap data and one exact HTTPS lookup, validates record/seed correspondence, excludes contact fields, and labels 0.85 confidence as registry-data confidence rather than identity confidence.
- Docker Verification run `38270478612` succeeded on commit `33185c7fbbe253562f6b644955bf2ff5ede79c0e`: `PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage`; `128 passed, 1 warning in 13.87s`; `DOCKER CAPTURE: PASS — 34/34 cases captured`. `results.json` had 34 entries with zero nonzero return codes and 34 stdout/stderr pairs. RDAP's offline health smoke returned 0. This verifies fixture/parser and container startup only; no live RDAP lookup occurred.
- Follow-up Docker Verification run `38272314026` succeeded on commit `e160c5e9fdee34ca0581b1cba3089cdbe2ae415c`, verifying the manifest's `verified-fixture` update and Florida documentation: `PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage`; `128 passed, 1 warning in 12.94s`; `DOCKER CAPTURE: PASS — 34/34 cases captured`. `results.json` SHA-256: `740F39E2FA0C9E4D1B4D8267CFD9F781C9DCB6A57000D03BA95930AA0B1D4ED5`.
- Final state commit `67d19e662a8830b3c392c2226e0d78ddcdd438a8` passed in Docker Verification run `38273505822`: `PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage`; `128 passed, 1 warning in 13.31s`; `DOCKER CAPTURE: PASS — 34/34 cases captured`. `results.json` SHA-256: `FAAF323A67FAB9FD1CEA1F1F252C98122FABBB7C62FDA08285F746980477FC2C`; 34 cases returned 0.
- State refresh commit `09ed1acfeac0167feff854cf77ccccbd0b882340` passed in Docker Verification run `38274729412`: `PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage`; `128 passed, 1 warning in 12.79s`; `DOCKER CAPTURE: PASS — 34/34 cases captured`. `results.json` SHA-256: `185C3643B8FE44774F2A743B8ACD8BE862632BEB2802EA6A4AA23AB18569AED5`; 34 cases returned 0.
- CI run `38269210962` first exposed a stale domain pending-adapter count (11 expected, 12 actual after RDAP became domain-capable). Updated the count and expected set in `tests/test_phase3_manifest.py`; no test was skipped or weakened.
- Updated the project policy documentation to the owner's Florida framework, retained the legal caveat that the project-defined floor is not a complete statement of law, and documented the Phase 9+ multi-seed roadmap. No adapter discovery registry or live investigation was changed/run.

## 2026-10-12 — Gravatar CI verification and state refresh
- Docker Verification run `38179832021` succeeded on commit `200ada277886ee961c90c668bfe4aa36fc5f2899`: parser preflight 32/32, `119 passed, 1 warning in 12.58s`, capture 33/33 with all return codes 0. Marked Gravatar `verified-fixture` (synthetic fixture and Docker health smoke only; no live API lookup).
- Added `*.egg-info/` and `ci-artifacts-*/` to `.gitignore`.
- Replaced the stale 2026-10-11 pause checkpoint in `HANDOFF.md` and `RESUME_STATE.json`. The Gravatar work had been committed (`200ada2`) after that checkpoint was written but before the state files were updated.
- Commit `593625bde90aed7b1d5b99d84acf4a995f0538b6` (message `-`, adding `AGENT_SETUP.md`, `AUTONOMOUS_DIRECTIVE.md`, and changelog lines) was a formatting slip in the commit message. It is already on origin, so it was not amended and history was not rewritten.
- The untracked `_rdap_draft.py` was kept, not deleted, because `phase5c.py` holds only the Gravatar adapter and the draft is the only copy of the RDAP code. The owner later retracted the delete instruction.
- Fixed a bug in my own manifest edit: `5976019` wrote `Fixture file:`, which fails `test_verified_fixture_adapter_notes_name_existing_fixture_file` (lowercase `fixture file: ` required). Caught by the local manifest test before any push and fixed in `131a3f3` as a new commit; the test was not changed.
- Split `RESUME_STATE.json` `last_commit` (actual HEAD) from the new `last_ci_verified_commit` (latest commit with a green CI run).

## 2026-10-11 — Phase 5c source review decisions
- Recorded Gravatar and RDAP as narrowly scoped public-data integrations to implement.
- Excluded ONYPHE per owner decision and excluded Mr.Holmes, IVRE, urlscan, ThreatCluster, and Social Analyzer where terms, source boundaries, or execution models could not be safely constrained.
- Recorded exact endpoint/scope conditions and official source links in `docs/PHASE_5C_REGISTRY.md`; no live target query or source scan was performed.
- Latest CI evidence entering this review: run `38172013706`, commit `5a64f428b8479dd497924d9e2c3f3d2acb402eda`.

## 2026-10-11 — Phase 5b source-review follow-up
- Docker Verification run `38171111124` succeeded on commit `76cbf765e2d3d2d491c12fea07648e7830b85d2b`: parser preflight 31/31, `110 passed, 1 warning in 12.55s`, capture 32/32, and all capture return codes were 0. Image build, tests, capture, and artifact upload succeeded.
- Applied the owner's exact source-scope conditions. Hudson Rock's documented username route returns credential fields; DarkNyx has no documented free metadata-only API and prohibits scraping; osint-darkweb-pkg cannot limit its query to the three approved indexes. These remain excluded.
- Reviewed Blackbird's current repository and Lullar's published checker. Blackbird has no declared upstream license; Lullar documents browser-side URL generation with manual profile opening rather than a machine-readable adapter interface. Both were excluded from integration.
- No new tool was installed, executed, or queried against a target. Phase 5b source review is complete; next is Phase 5c proposal verification.

## 2026-10-11 — XposedOrNot CI follow-up
- Docker Verification run `38167558342` built all pinned images and captured all 32 cases with return code 0, but the pytest suite exposed a stale cumulative Phase 5 registry-size assertion (`26` actual versus `25` expected).
- Updated only the expected registry size to 26; no test behavior or assertion was weakened.

## 2026-10-11 — XposedOrNot fixture verification
- Docker Verification run `38168341113` on commit `d9b3fe9afc9c7b28be37c8c1a5ae601c481fa59c` passed: 110 tests, parser preflight 31/31, and Docker capture 32/32 with all return codes 0.
- Marked XposedOrNot `verified-fixture`; no live API lookup occurred and its fixture remains synthetic.
- Follow-up run `38169040308` verified the manifest and documentation update with 110 tests passing, parser preflight 31/31, and Docker capture 32/32.

## 2026-10-11 — PhoneInfoga scope review
- Checked the exact v2.11.0 CLI, scanner registration, scanner docs, OVH endpoint, and GPL-3.0 license from upstream.
- Recorded the no-key scope (local parsing, Google search-link generation only, OVH public range lookup); Aletheia does not forward PhoneInfoga API credentials. No live phone scan was made.
- Recorded the current parser's omission of Google URLs and OVH fields as a deferred completeness issue.
- Docker Verification run `38170483392` verified the documentation and manifest update: 110 passed, parser preflight 31/31, and Docker capture 32/32 with all return codes 0.

## 2026-10-11 — Phase 5b scoped-source review
- Verified the documented, no-key XposedOrNot email check route and constrained its proposal to the default, non-detailed response.
- Excluded Hudson Rock, DarkNyx, and osint-darkweb-pkg from the active Phase 5b registry because their documented access paths could not be verified as stable Tier 1–2-only scopes.
- Recorded official-source URLs and the statically inspected PyPI source archive hash in `docs/NOT_INTEGRATED.md`; no candidate package was installed or run.

## 2026-10-11 — XposedOrNot implementation prepared (CI pending)
- Added the XposedOrNot email adapter, isolated standard-library Docker runner, parser fixture from the official documentation example, and parser/authorization/Docker health coverage.
- Added its build target and manifest entry. The manifest remains `unknown` until CI confirms the new fixture tests; no live email lookup was made.

## 2026-10-11 — Phase 5b startup checkpoint
- Created `RESUME_STATE.json` and this handoff checkpoint for the autonomous completion directive.
- Resolved the LeakCheck gate as excluded, per project-owner decision; no adapter or lookup was created.
- Recorded current remote CI evidence and the unverified local commits in `HANDOFF.md`.
- Corrected the Phase 5b registry and project direction to reflect the LeakCheck exclusion.

## 0.7.0 — Phase 7
- Added SQLite benchmark store for labeled quality cases and execution telemetry.
- Added benchmark leaderboard API and CLI.
- Added local interactive graph web UI.
- Added local stdio JSON-RPC MCP bridge for Aletheia control-plane actions.
- Integrated adapter execution timing into benchmark telemetry.
- Updated core API Docker image to run the FastAPI service.
- Docker build/run remains pending because this environment has no Docker CLI/socket.

# Changelog

## 2026-10-11 — Pause checkpoint (Gravatar draft in progress)
- Recorded the latest verified commit/run and the exact state of the incomplete, unverified Gravatar draft in `HANDOFF.md` and `RESUME_STATE.json`.
- No code, tests, commits, pushes, or CI runs were performed for this checkpoint; current source changes remain local and unverified.

## 0.6.0 — Phase 6
- Added SEC EDGAR, GLEIF, OpenCorporates, OpenSanctions, and CourtListener adapters.
- Added company/legal-entity/LEI/filing/court-case/sanction/jurisdiction graph entity types.
- Added `name` seed routing.
- Added per-adapter legal/license metadata and five Docker image boundaries.
- Kept sanctions relevance scores distinct from identity probability and court-search results as discovery leads.
- Docker build/run remains pending because this environment has no Docker CLI/socket.

# Changelog

## 0.5.0 — Phase 5

- Added eight isolated social/geospatial/image adapters: Instaloader 4.15.3, Reddit API v1, YouTube Data API v3, Overpass, SunCalc 2.0.2, DeepFace 0.0.101, InsightFace 2.1, and Google Cloud Vision 3.16.0.
- Added public-only Instagram profile metadata handling with no login/cookie/private-profile path.
- Added official OAuth/API-key runners for Reddit, YouTube, and Google Cloud Vision with secret-safe environment handling.
- Added geolocation seed type plus coordinate normalization and read-only Overpass/SunCalc processing.
- Added image seed type and staged operator-supplied images into isolated workspaces.
- Restricted DeepFace/InsightFace to face detection only; no person identification, remote face search, or demographic inference is produced.
- Made InsightFace network-disabled so model weights cannot be fetched silently at runtime.
- Added eight Phase 5 Docker health-smoke tests and parser/contract/staging tests.
- Added Phase 5 manifest, validation, legal notes, and handoff.

## 0.4.0 — Phase 4

- Added seven isolated identity/email/phone adapters: Maigret 0.6.6, Holehe 1.61, h8mail 2.5.6, HIBP API v3, PhoneInfoga 2.11.0, libphonenumber 9.0.40, and Twilio Lookup v2 Basic Lookup.
- Added per-adapter Dockerfiles, runner boundaries, license metadata, and legal notes.
- Added explicit authorization assertions for personal-identifier lookups; offline libphonenumber remains network-free.
- Added conservative identity parsing: only claimed/positive signals become graph findings.
- Added phone seed normalization for E.164-style values without ownership inference.
- Added secret-safe Docker environment propagation so API secrets do not enter Docker argv or audit command records.
- Added Phase 4 parser, contract, authorization, secret-handling, and Docker smoke tests.
- Rejected WhatsMyName as a checker integration because current upstream distribution is dataset-oriented and bundled checker scripts were removed; no replacement checker was implemented.
# 2026-10-16 — Pause at darkweb_search source review

- Recorded the user-requested pause and exact resume point in `HANDOFF.md` / `RESUME_STATE.json`.
- No repository implementation files were changed. Preliminary review: Piano 0.1.2 PyPI sdist hash matched the published SHA-256; Ahmia current terms prohibit scraping; TorBot is a page crawler; Intelligence X requires a registered API key. No live requests were made.
- Docker Verification run `38902790400` was still `in_progress` at last check; evidence must be downloaded and read before claiming its outcome.

