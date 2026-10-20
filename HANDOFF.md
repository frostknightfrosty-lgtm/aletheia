# Aletheia Handoff — Phase 17 staged (pivot cascade + source completeness; autonomous campaign)

Last updated: 2026-10-20T22:02:00Z

## Project boundaries

Aletheia is a free, open-source OSINT investigation platform under the Florida project
policy (`docs/DIRECTIVE_AMENDMENT_FLORIDA.md`). Sources sit on five tiers; the only project
gate is the Tier 5 hard floor: unauthorized computer access (including another person's
credentials or CAPTCHA/paywall bypass), communications interception, criminal marketplace
transactions, and stalking/harassment. Tier 1–4 sources run by default when their
prerequisites are met. A tier classification is project policy, not a legal conclusion.

## Repository and CI state

- **Newest CI-verified close-out: `c1f8cde`** (final docs/state tree; docker
  verification run **39499810107** green — parser 62/62; **1175 passed**;
  capture 96/96; egress 62/55/55 wired; storage 6/6; 96 results, 0 nonzero).
  No live source run occurred. The final report is
  `docs/FINAL_REPORT_PHASE17.md`.
- **Newest CI-verified code commit: `9c9cd9c`** (minecraft adapter; run
  **39495727637** green — parser 62/62; 1175 passed; capture 96/96; egress
  62/55/55 wired; storage 6/6). Immediately prior:
  `82a4049` (pgp_keys; run **39494804791** — parser 61/61; 1167 passed;
  capture 93/93; egress 61/54/54; storage 6/6), `58aa354` (github_identity;
  run **39493701837** — parser 60/60; 1158 passed; capture 90/90; egress
  60/53/53; storage 6/6), `503b431` (weather; run **39487437707** — parser
  59/59; 1149 passed; capture 87/87; egress 59/52/52; storage 6/6), and
  `ceaf595` (researcher_ids; run **39484536317** — parser 58/58; 1141 passed;
  capture 84/84; egress 58/51/51; storage 6/6). All five are fixture-only; no
  live source lookup occurred.
- Latest CI-verified commit before those: `5ddf240` (ShadowFinder adapter; docker
  verification run **39448325747** green — parser 55/55; **1112 passed**;
  capture 75/75; egress 55/49/49 wired; storage 6/6; docs `c169b1e` verified by
  run **39451409086** with the same numbers; state verification pending).
  Earlier: `0ac22ed` (tracelines; run **39416003189**: parser 54/54, 1100
  passed, capture 73/73, egress 54/49/49, storage 6/6; docs `e02c181` and state
  `8df6901` verified by runs **39418791588** and **39421156802**, the latter on
  a second attempt after a transient crtsh egress flake); `19db818`
  (PicImageSearch; run **39404418732**: parser 53/53, 1089 passed, capture
  71/71, egress 48/48 wired, storage 6/6; docs `6d2a049` and state `0bb8dbc`
  verified by runs **39407226773** and **39410068828**); `0015ea4` (VENOM;
  run **39196608448**; its docs/state push `da0283f` ran **39325135904**,
  green after three transient Go module-verification failures); `fedfd64`
  (tiktok-hashtag; run **39174382751**; its docs/state push `de1a51e` ran
  **39195856352**).
- **CI capacity restored (2026-10-20):** the repository was made public
  (`private: false`), so standard GitHub-hosted runners are free; the blocked
  tracelines run executed. Its first real attempt exposed a genuine image
  defect — Python 3.11 could not install `networkx==3.7` — fixed in `0ac22ed`
  by building on Python 3.12. The blocker record remains in
  `docs/USER_ACTIONS.md` §0 as resolved; the parked queue (§6) was removed.
- The authorized live run **39141366670** ran on tree `8939517` and is green (37m19s) —
  see the live-audit section below.
- Newest artifact check (run **39448325747**, commit `5ddf240`): lines copied
  from the downloaded artifact (`ci-artifacts-39448325747`), not typed —
  `PARSER PREFLIGHT: PASS — 55/55 adapters have parser coverage`; `1112 passed,
  1 warning`; `DOCKER CAPTURE: PASS — 75/75 cases captured` (including
  `phase17-shadowfinder-health` — stdout `ok`, `pin_file: true`,
  `grid_resolution_deg: 0.5`, `grid_cells: 208800`, `network_imports: []` — and
  `phase17-shadowfinder-selftest`, 9/9 checks including a real 3×3 solar
  computation); `egress-scenario.json`: `adapters=55 network_required=49
  wired=49`; `storage-conformance.json`: `passing` = file, postgres, neo4j,
  elasticsearch, minio, redis, `unconfigured` = [], `required_all` = `true`;
  `pytest-summary.json`: `junit_total` 1112, `skipped_in_ci` [], `ok` `true`;
  `results.json`: 75 entries, 0 nonzero return codes. The docs commit `c169b1e`
  repeated the same numbers in run **39451409086** (parser 55/55; 1112 passed;
  capture 75/75; egress 55/49/49; storage 6/6).
- Newest artifact check (run **39457146650**, commit `4505ae5`): lines copied
  from the downloaded artifact (`ci-artifacts-39457146650`), not typed —
  `PARSER PREFLIGHT: PASS — 56/56 adapters have parser coverage`; `1122 passed,
  1 warning`; `DOCKER CAPTURE: PASS — 78/78 cases captured` (including
  `phase17-pybdshadow-health` — stdout `ok`, `pin_file: true`, package `0.3.5`,
  geopandas `1.2.0`, pyproj `3.8.0`, shapely `2.2.0` — and
  `phase17-pybdshadow-selftest`, 8/8 checks including a real synthetic shadow
  computation); `egress-scenario.json`: `adapters=56 network_required=49
  wired=49`; `storage-conformance.json`: `passing` = file, postgres, neo4j,
  elasticsearch, minio, redis, `unconfigured` = [], `required_all` = `true`;
  `pytest-summary.json`: `junit_total` 1122, `skipped_in_ci` [], `ok` `true`;
  `results.json`: 78 entries, 0 nonzero return codes. The docs commit `b5bc16c`
  repeated the same numbers in run **39460496509** (parser 56/56; 1122 passed;
  capture 78/78; egress 56/49/49; storage 6/6).
- Newest artifact check (run **39466252253**, commit `446ccab`): lines copied
  from the downloaded artifact (`ci-artifacts-39466252253`), not typed —
  `PARSER PREFLIGHT: PASS — 57/57 adapters have parser coverage`; `1132 passed,
  1 warning`; `DOCKER CAPTURE: PASS — 81/81 cases captured` (including
  `phase17-crypttrace-health` — stdout `ok`, `pin_file: true`, package `0.22.0`
  — `phase17-crypttrace-selftest`, 8/8 checks including Bitcoin address
  validation and report normalization, and the offline
  `phase17-crypttrace-normalize` case under `--network none`);
  `egress-scenario.json`: `adapters=57 network_required=50 wired=50`;
  `storage-conformance.json`: `passing` = file, postgres, neo4j, elasticsearch,
  minio, redis, `required_all` = `true`; `pytest-summary.json`: `junit_total`
  1132, `skipped_in_ci` [], `ok` `true`; `results.json`: 81 entries, 0 nonzero
  return codes. The docs commit `1df7750` repeated the same numbers in run
  **39468982807** (parser 57/57; 1132 passed; capture 81/81; egress 57/50/50;
  storage 6/6).
- **researcher_ids unit verified:** commit `ceaf595` — keyless Wikidata +
  ORCID public-researcher adapter, one bounded name query per source (max 5
  results each), ORCID email arrays discarded, lead-only confidence. Manifest
  `verified-fixture`; run **39484536317** (parser 58/58; 1141 passed; capture
  84/84; egress 58/51/51; storage 6/6; 84 results, 0 nonzero). No live target.
- **weather unit verified:** commit `503b431` — Open-Meteo forecast and
  historical-archive adapter, one coordinate/date per run, non-commercial free
  tier, CC-BY 4.0 attribution on every finding. Manifest `verified-fixture`;
  run **39487437707** (parser 59/59; 1149 passed; capture 87/87; egress
  59/52/52; storage 6/6; 87 results, 0 nonzero). No live target.
- P17.12 audit: `docs/COMPLETENESS_AUDIT.md`, committed as `aa99eaa` and
  verified by run **39472065798** (documents-only; same 57/57, 1132 passed,
  81/81, 57/50/50, 6/6).
- **tracelines unit verified:** commit `0ac22ed` (the unit's first code commit
  `89c6400` plus the Python-3.12 image fix). Local evidence before commit:
  parser preflight 54/54; suite 1030 passed + 70 environment-only skips = 1100;
  the CI container run confirms `pin_file: true` and 10/10 selftest checks. The
  manifest entry is `verified-fixture` with the run citation; docs `e02c181` and
  state `8df6901` were verified by runs **39418791588** and **39421156802**
  (the latter on a second attempt after a transient crtsh egress flake).
- **ShadowFinder unit verified:** commit `5ddf240` (the unit's first code
  commit `0eca2b4` plus the selftest-contract fix) — offline solar-geometry
  adapter over the pinned Bellingcat package (MIT, tag v0.7.1, commit
  `215485a`), new `SeedType.SHADOW_OBSERVATION`, tier 1, no network. Local:
  parser preflight 55/55; suite 1041 passed + 71 skipped = 1112. The first run
  (`0eca2b4`, run `39444978518`) passed the image build, health, parser and
  suite but failed the selftest's `target_validation` assertion; the fixed
  check exercises `_parse_args` + `_parse_observation`, and a regression test
  pins it. Manifest `verified-fixture`; docs `c169b1e` verified by run
  **39451409086**; the state push is the last step.
- **pybdshadow unit verified:** commit `4505ae5` — offline building-shadow
  adapter over pybdshadow 0.3.5 (BSD-3-Clause, commit `e2665ee`), file-seed
  JSON input, tier 1, no network. Local: parser 56/56; suite 1050 passed + 72
  skipped = 1122; the CI container run confirms `pin_file: true`, 8/8 selftest
  checks and a real synthetic shadow computation. Manifest `verified-fixture`;
  docs `b5bc16c` verified by run **39460496509**; state `c217cf5` verified by
  run **39463410774**; unit complete. GeoLocator (#18) was recorded in the same
  docs commit as an upstream-withdrawal blocker: the official
  TIBHannover/GeoEstimation repository removed all source and model weights,
  the checkpoint URLs return HTTP 404, and no code was built.
- **crypttrace unit verified:** commit `446ccab` — Bitcoin-only fund-flow
  adapter over crypttrace 0.22.0 (MIT, commit `cf60a88`),
  `SeedType.CRYPTO_ADDRESS`, depth 2 / branching 3, no API key; manifest 60
  entries / 57 adapters. Local: parser 57/57; suite 1059 passed + 73 skipped =
  1132; driver health and 8/8 selftest checks pass against the pinned package
  in an isolated venv. Manifest `verified-fixture`; docs `1df7750` verified by
  run **39468982807**; the final state push is the last step.
- **P17.11/P17.12 closed:** 83 of 111 sources wired; 28 remain with written
  gate/owner/blocker reasons (audit `docs/COMPLETENESS_AUDIT.md`, run
  **39472065798**). **P17.13 is complete for all adoptable free sources:**
  `researcher_ids` (Wikidata + ORCID), `weather` (Open-Meteo + historical),
  `github_identity` (GitHub endpoints + `.keys`), `pgp_keys` (WKD), and
  `minecraft` (Mojang current profile) are CI-verified and
  `verified-fixture`. NameMC, social-graph list ingestion, and news_search are
  written exclusions in `docs/NOT_INTEGRATED.md`; Wayback CDX and
  WhatsMyName-style lists were already covered. No free P17.13 adapter remains
  unbuilt. Waves B–D stay owner-gated.
- Evidence lines copied from the downloaded artifact of run `39141365915`
  (`ci-artifacts-39141365915`), not typed:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - `786 passed, 1 warning`
  - `DOCKER CAPTURE: PASS — 60/60 cases captured`
  - `STORAGE CONFORMANCE: PASS — 6/6 backends conform`
- `pytest-summary.json`: `junit_total` 786, `failed` `[]`, `skipped_in_ci` `[]`, `ok`
  `true`. `egress-scenario.json`: all 9 checks ok, chain `valid: true` with `log_entries`
  7 = `egress_events` 7; `phase15-egress-policy-covers-registry` = `adapters=49
  network_required=44 wired=44`; the crtsh check returned `new CONNECT crt.sh entries=1
  status=200` this run; the four `phase12-*` checks pass.
- Local consistency at the crypttrace-verified tree: **1059 passed + 73 skipped = 1132**,
  which equals the CI passed count exactly. The 73 skips are 68 Docker-dependent
  tests (no Docker on this machine, including the crypttrace and pybdshadow
  container-health cases) and 5 `tests/test_storage_services.py` (no
  `ALETHEIA_STORAGE_*` service configured); both groups execute in CI, and CI
  now *fails* if either group skips — see `docs/SKIPPED_IN_CI.md`.
- Local consistency at the final tree: **1097 passed + 78 skipped = 1175**,
  which equals the CI passed count exactly. The 78 skips are 73
  Docker-dependent tests (including the researcher_ids, weather,
  github_identity, pgp_keys and minecraft health cases) and the same 5
  storage-service tests; all execute in CI.
- 62 registered adapters; all 62 are `verified-fixture` in
  `PROJECT_MANIFEST.json`. Three manifest entries are non-adapter entries
  (`egress_proxy` plus two libraries), for 65 tool-inventory entries total.
  Six storage backends, all conformance-verified
  against real services in CI. 55 of the 62 adapters declare
  `network_required=True`, and the egress policy wires all 55.
- Tracker: 83 of 111 sources wired, 28 remaining — all owner-gated
  (Gate 3/Gate 6/Gate 7) or recorded drops/blockers. See
  `docs/COMPLETENESS_AUDIT.md`.
- No unverified unit remains in the working tree and no adoptable free P17.13
  adapter remains. NameMC, social-graph list ingestion, and news_search are
  written exclusions in `docs/NOT_INTEGRATED.md`; Waves B–D are owner-gated.

## Phase 17 — pivot cascade + source completeness (staged 2026-10-18; autonomous campaign)

Where older sections of this file describe next steps, **this section and
`docs/CAMPAIGN_LOG.md` supersede them.**

Design of record: `docs/PIVOT_CASCADE.md` v3 (+ the 2026-10-18 directive addendum) —
any seed (seed list / raw text / screenshot) → evidence-gated adapter→adapter chaining
→ tiered identity map to exhaustion, every step evidence-gated. Owner directive of
2026-10-18: everything in the 111 accepted candidates and every policy-permitted
not-yet-integrated source becomes fully integrated, wired and working — tracked
item-by-item in `docs/SOURCE_COMPLETENESS.md` (83 of 111 already built; 28 gaps;
§B policy-permitted set; §C owner actions; §D recorded blockers).

Both were recorded in docs commits `61cd60d` → `b6ad26d` → `c4faa40` (each
CI-verified). The owner then mandated a **fully autonomous campaign** (2026-10-18
evening): execute the entire remaining plan — P17.2–P17.9 cascade engine, P17.10
(fixture/local/CI first; the live segment runs on the owner's own authorized seed),
P17.11–P17.12 completeness, P17.13 horizon completion, close-out — and stop only when
nothing remains but owner-gated items.

- Campaign anchors: `docs/CAMPAIGN_LOG.md` (journal + queue + landmines — read after
  every compaction) and `docs/USER_ACTIONS.md` (the only owner-gated items: free-key
  registrations, provider permissions, owner confirmations, redlines).
- Provisional defaults adopted by the campaign unless the owner redlines: adaptive
  depth 3 → 5 on HARD in owner mode; owner-mode pivots email/name/phone on; case model
  opt-in (`--case X`); cache TTL 30d profiles / 7d DNS; face search
  corroboration-only; completeness waves keyless-first A → E.
- Live policy during the campaign: live runs only for targets whose Gate 2 assertion
  is already on file (`username:frost2233`); every other target parks. No
  `verification_status` moves except from copied artifact lines (Gate 5).

## Authorized live self-audit of `username:frost2233` (2026-10-18, complete)

The owner opened Gate 2 for one target with an assertion recorded verbatim in the live run's
`MANIFEST.json`: *"Self-audit: I am the owner of the Discord account with username frost2233
and I authorize an investigation of my own username across public, legal, open sources."*

- **The live path took five repair commits to get there**: `4583d38` (after the first live
  attempt `39120709419`), `1919266` (after `39125383530`), `692e418` (the CI-only defects
  found by Docker Verification run `39128092472`), `b5ff9e2` and `de6b218` (after the
  diagnostic run `39135219248`). Each was verified by its own CI run; the top CHANGELOG
  entry carries every copied number.
- **What the final run produced** (run `39141366670` on tree `8939517`, green, 37m19s; run
  directory `983cc23b-f9f6-4ccd-8483-82f7e37738ba`): 16 sherlock sites; 19 maigret accounts
  with extended info from 9; report `entity_count` 32, `edge_count` 43,
  `resolution_candidate_count` 3 (all left as candidates — nothing is auto-merged on fuzzy
  similarity); `report.json`, `report.pdf`, `report.stix2.json`, `graph.graphml`; a
  hash-chained `AUDIT.jsonl` with `chain_tip`
  `894354635d9da9789ea35d0a4798816d7338134c4ad2918569a0c02e4e5c9cbe`.
- **Extended attributes returned**: Pinterest (`Helen Frost`, created 2014-05-25, latest
  activity 2025-07-10, 67 posts), Twitter (`frost`, created 2016-01-03, protected), Twitch
  (channel created 2013-01-31), Snapchat (`Frosti`), Picsart (`frost`), TikTok, Telegram
  (`Frost2233`), Chess.com (`Leon Barnard`, ZA, created 2025-02-12), Xvideos (`Frost2233`,
  BD, created 2018-06-17). Maigret tag summary: countries `ru`, `bd`; 24 interest tags.
- **Candidate caveat (recorded, not softened):** every hit is a same-username *candidate*,
  not proof of ownership. Display names differ across platforms (`Helen Frost`,
  `Leon Barnard`, `Frosti`, `frost`), and the resolver's own candidate set includes obvious
  site-name coincidences (`kick.com` vs `ko-fi.com`; `twitchtracker.com` vs `twitter.com`).
  Discord's unauthenticated username-attempt endpoint reported the handle as taken, but
  Discord exposes no public profile URL, so its recorded URL is the site root — a
  username-exists signal, not a linkable profile.
- **Honest limits:** `instaloader` still ends on Instagram's side (`429 Too Many Requests`);
  `social_username` egresses correctly (2 entries, both HTTP 200) but both sources returned
  nothing usable (octosuite: `HTTP 403` inside the tunnel — GitHub's unauthenticated limit;
  masto: no finding); `reddit-api`, `youtube-api` and `leak_checkers` remain key-gated skips
  (Gate 3). No `verification_status` in `PROJECT_MANIFEST.json` was changed.

## Phase 16 — multi-seed investigations and context features (complete)

Implemented and CI-verified in commit `f0352a4` (single code commit). The
non-gated deliverables from `docs/PROJECT_DIRECTION.md` are now implemented; the
gated ones remain gated.

- **Multi-seed runs.** `Orchestrator.create_run` accepts a `Seed` (unchanged) or
  a sequence; `manifest["pending_seeds"]` schedules every matching adapter once
  per supported seed, each seed expands into its own workspace
  (`adapter@seedN`, 1-based) and `result.json`, and every finding is tagged with
  `Provenance.seed_index` before ingestion. Single-seed runs keep the previous
  artifact shape (untagged provenance, unchanged workspace names and
  `tools_invoked` labels); legacy manifests without `pending_seeds` remain
  resumable.
- **Intersection pass.** `EntityResolver.resolve` reads per-entity seed
  attribution from edge provenance and applies a bounded boost
  (`score * (1 + 0.05 * (trees - 1))`, capped at 1.0) when an entity is
  corroborated by two or more trees. The boost never creates a candidate (the raw
  threshold is applied first) and never feeds the Phase 13 calibrator; the
  candidate explanation records `cross_seed_trees` and
  `cross_seed_boost=<raw>-><boosted>` and states it is a heuristic prior. See
  `docs/MULTI_SEED.md`.
- **Context filters** (country, age min/max, language, timezone) live in the
  manifest as `context_filters`, ride on every `AdapterRunRequest`, and are
  enforced at resolution: only positive mismatches flip a candidate to
  `filtered_out` with a `context_filter_mismatch=...` explanation; an entity
  with no comparable attribute is never excluded. No ISO-3166 dataset is bundled
  and no adapter consumes the filters as query hints yet.
- **Jurisdiction warnings** (`app/aletheia/core/warnings.py`,
  `docs/JURISDICTION_WARNINGS.md`): strong-privacy jurisdiction, minor,
  health-data, and protected-class heuristics over seeds and entity attributes,
  deduplicated, recorded as `jurisdiction_warning` audit events (before
  `phase2_finalize`, same hash chain), in `report.json`, and in the PDF. They
  never gate a run and are not a legal determination.
- **Adapter-run reporting.** `resume` persists adapter-recorded sub-source skips
  (missing keys, retired endpoints, paid-only APIs) to `manifest["skipped"]`;
  `report.json`/`report.pdf` list every matching adapter with its outcome and
  each skip reason, and mark failed and still-pending adapters.
- **Lawful basis.** Every `resume` records a `lawful_basis_declaration` audit
  event (declared true/false plus the assertion text when present); an empty
  declaration does not stop a run.
- **Tier enforcement.** `PROJECT_MANIFEST.json` validation requires
  `legal_tier` (integer 1..5), `enabled_by_default`, and `batch_grouping` for
  every adapter entry, with a non-empty `disabled_reason` when
  `enabled_by_default` is false (all 49 adapter entries pass); the registry
  refuses to construct an adapter whose entry declares `legal_tier=5`.
- **CLI/API/MCP.** Repeatable `--seed`, plus
  `--filter-country|--filter-age-min|--filter-age-max|--filter-language|--filter-timezone`;
  the HTTP API and the MCP `investigate` tool take `seeds` + `context_filters`.
- 36 new tests (`tests/test_multi_seed.py`, `tests/test_jurisdiction_warnings.py`,
  `tests/test_tier_metadata.py`); no test skipped, deleted, or weakened.

### Honest limitations (recorded, not softened)

- The trees share one graph, one audit chain, and one run directory; "independent
  tree" is provenance tagging, not separate storage.
- The 5%-per-tree boost is a documented heuristic prior, not a calibrated
  probability and not source evidence.
- Context filters exclude only on positive attribute mismatches; the matching
  rules are documented and have no ISO dataset behind them.
- Jurisdiction warnings are keyword/attribute heuristics with expected false
  positives and false negatives; they are informational only.

## Phase 15 — egress proxy coverage (complete)

Implemented and CI-verified in commits `5add1b5` (policy, default wiring, CLI flag), `4ed8772`
(docs), `9f1c092` (report the policy check), `d7f73e1` (harden the crtsh check).

- The Phase 12 allowlist `EGRESS_WIRED_ADAPTERS = (search_engines, ssl_tls, ip_intelligence)`
  is gone. `egress.is_wired(name, network_required=descriptor.network_required)` is true for
  every adapter whose descriptor declares `network_required=True`; `EGRESS_EXEMPT_ADAPTERS` is
  the empty, documented exception list. Registry measurement: 49 adapters, 44
  network-requiring, 44 wired.
- `Orchestrator.resume` wires **by default**. That is a production-path change: previously
  `wire_egress` defaulted to `False`, and neither `aletheia investigate` / `aletheia resume` nor
  the MCP server passed it, so the proxy was effectively test-only outside
  `ci/egress_scenario.py`. Offline replays pass `wire_egress=False`; the CLI exposes
  `--no-egress-proxy`.
- Coverage is checked rather than asserted: a unit test walks the registry, and CI reports
  `phase15-egress-policy-covers-registry` (`adapters=49 network_required=44 wired=44`) plus a
  real-container check that runs `crtsh` — never in the Phase 12 allowlist — on an `--internal`
  network and finds its HTTPS attempt in the proxy log (`crtsh rc=1 new CONNECT crt.sh entries=1 status=502`,
  fail-closed).
- The wiring pattern itself is unchanged from Phase 12: one `--internal` network per adapter
  run, the proxy as the only route out, `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` in the container,
  the proxy log appended to the run's hash-chained `AUDIT.jsonl`, then the proxy stopped and the
  network removed.

### Honest limitations (recorded, not softened)

- Coverage is complete **by policy**: every network-requiring adapter is classified from its
  descriptor. The proxied path is proven end to end for four adapters (`search_engines`,
  `ssl_tls`, `ip_intelligence`, `crtsh`). An adapter whose client ignores the proxy variables
  (or speaks a non-HTTP protocol) fails closed on the `--internal` network instead of egressing
  unproxied; that failure mode is not separately demonstrated per adapter.
- Some adapters wrap third-party CLIs (`sherlock`, `theharvester`, `amass`, …) that may use
  their own resolvers; the network policy still removes any route out, so the worst case is a
  failed lookup, not an unlogged request.
- The proxy log records what reached the proxy; it cannot see inside an established TLS tunnel
  and is not a packet capture.

## Phase 14 — storage backends (complete)

Implemented and CI-verified in commits `c87f52f` (contract + six backends), `597428f`
(prove every test ran; fix the service startup), `e9bfdda` (the two defects CI found).

- `app/aletheia/storage/base.py` — `StorageBackend`, one narrow contract covering the two
  artefacts the directive names: graph snapshots and run manifests. Backends store whole JSON
  documents so a snapshot round-trips byte-for-byte, rather than forcing a universal
  normalised schema. `MigrationRunner` applies ordered migrations once, records
  `(version, name, checksum, applied_at)`, and raises `MigrationError` on checksum or name
  drift. `prepare_migrations()` runs before the runner reads that log, because the log table
  cannot be created by a migration the runner has not yet read.
- Backends: `file_store.py` (`FileGraphStore`, the default the orchestrator uses),
  `postgres_store.py` (JSONB tables through `pg8000`), `neo4j_store.py` (JSON snapshot plus
  native `(:AletheiaEntity)`/`[:RELATED]` materialisation scoped by `run_id`, with
  `verify_materialised()` as the conformance hook), `elasticsearch_store.py` (indexed
  documents with a real `search_entities` field query), `minio_store.py` (one JSON object per
  run), `redis_store.py` (namespaced keys, `scan`-based listing).
- `app/aletheia/storage/conformance.py` — the single shared contract, used by both the pytest
  suite and the CI evidence script so they cannot drift, plus a `BrokenBackend` negative
  control proving the contract can fail. `tests/test_storage.py` (15 tests) and
  `tests/test_storage_services.py` (5 tests, one per service) consume it.
- CLI: `aletheia storage health|migrate|sync`. `sync` applies the backend's migrations first,
  so mirroring into a brand-new database works in one step.
- `docs/STORAGE_BACKENDS.md` — contract, backend table, migration runner, CLI, verification
  path, and the honest limits below.

### Honest limitations (recorded, not softened)

- The hash-chained `AUDIT.jsonl` stays on local disk. Its tamper-evidence depends on atomic
  `fsync` appends; no backend stores it in this phase.
- The orchestrator still writes through `FileGraphStore` by default. Networked backends are
  populated via `aletheia storage sync` (or the Python API) — the pipeline is not yet wired to
  write to them directly.
- Redis is a fast-path cache, not a system of record; `minio` is verified against an
  S3-protocol server, not a MinIO server (see below).
- **MinIO substitution, disclosed:** `minio/minio` returns 404 on Docker Hub (the image was
  deleted in 2026-09) and `quay.io/minio/minio` refuses anonymous pulls, so CI verifies the S3
  code path (`minio-py`) against `adobe/s3mock:5.2.3`, a real S3-protocol server, rather than
  against a MinIO server. This is recorded in `docs/STORAGE_BACKENDS.md`, `docker-compose.yml`
  and `RESUME_STATE.json`; supplying Quay credentials or another S3 endpoint would let the
  same code path be verified against MinIO itself.

### Defects CI found that local runs could not

1. PostgreSQL health always returned `ok: false`. pg8000's protocol layer builds every row as
   a Python `list` (`pg8000/core.py`, `handle_DATA_ROW`), so `SELECT 1` yields `[[1]]`, and the
   check compared that against the literal `[(1,)]`. `_fetchall` now normalises rows to
   tuples and `health()` compares values and records what it saw.
2. `MigrationRunner.run()` read `aletheia_schema_migrations` before applying anything, while
   migration 1 was what created that table, so `migrate` failed with
   `relation "aletheia_schema_migrations" does not exist` on a fresh database.
3. A unit test asserted the developer machine's environment (every backend variable unset) and
   therefore failed in CI, where all of them are set.

All three are fixed and pinned by tests that need no server: runner ordering, the exact
pg8000 row shape, a configured-but-unreachable backend, and `sync` applying migrations first.

### CI now proves execution, not just success

- `ci/pytest_summary.py` cross-checks the run's JUnit XML against the pytest console summary
  and **fails the job if any test skipped**. It exists because a storage service that failed to
  start would otherwise make its test skip while CI still reported success.
- `ci/storage_conformance.py --require-all` fails when a backend is unconfigured. Run
  `39078543221` reported `STORAGE CONFORMANCE: PASS` while no service had started at all.
- The workflow frees the runner's unused SDKs before building (`ci-artifacts/disk-space.txt`
  records 13 GB free before and 35 GB after; the earlier run died with `no space left on
  device` while pulling the Elasticsearch image) and captures the service logs as evidence.
- `docs/SKIPPED_IN_CI.md` documents why 59 tests skip locally and never in CI.
- Run `39079850431` was the first run in which all 54 Docker integration tests and all 5
  storage service tests actually executed: 665 cases, 0 skipped, and the two failures it
  reported were genuine defects rather than skips.

## Phase 13 — score calibration (complete)

Implemented and CI-verified in commit `f1a9a84`.

- `app/aletheia/core/calibration.py` — new. `PlattScaling` fits `sigmoid(slope * score +
  intercept)` by Newton-Raphson on Platt-smoothed targets; `IsotonicRegression` fits a
  monotone step function by pool-adjacent-violators. Both are pure standard library (the
  project installs no numeric package). `Calibrator` wraps them and keeps `trained` `False`
  below `MIN_LABELED_PAIRS = 8` pairs or when a class is missing, so an untrained model is
  never presented as a probability. Dict round-trip via `to_dict`/`from_dict`.
- `app/aletheia/phase2/resolution.py` — `EntityResolver` takes an optional `Calibrator` and
  reports `calibrated` / `calibrated_probability` per `SAME_AS_CANDIDATE` edge
  (`attributes.resolution`). Without a trained calibrator these are `false` / `null` and the
  raw Jaro-Winkler/Levenshtein composite is retained as a similarity score.
- `tests/test_calibration.py` — 18 tests (monotonicity, boundedness, degenerate input,
  serialization round-trip, untrained-honesty, resolver integration).
- `tests/fixtures/calibration_pairs.json` — 80 **synthetic** labelled pairs, deterministically
  generated (seed 20261017). This is not real investigation data.
- `docs/ADAPTER_CONTRACT.md` — new "Calibrated vs uncalibrated scores" section.
- Honest limitation: the fixture is synthetic, so the fitted probabilities demonstrate the
  mechanism only; real calibration is deferred until labelled pairs from authorised
  investigations exist. The `calibrated` flag and the component contract are the stable part.

## Phase 12 — egress proxy wiring (complete)

Implemented and CI-verified in commit `ccd5a4b`.

- `app/aletheia/core/egress.py` — added `ProxySession` (creates an `--internal` Docker
  network and starts the detached proxy on it, no published host port), `create_network_command`,
  `remove_network_command`, `network_name`, `EGRESS_WIRED_ADAPTERS`, `is_wired`, and a
  DNS-safe container name (underscores become hyphens, because DNS labels cannot carry them).
  `EgressProxy.run_command` gained `detached` and `publish_port`.
- `app/aletheia/core/execution.py` — `run_docker(..., network_name=...)` joins a named
  network (the internal one), overriding the old `bridge`/`none` choice.
- `app/aletheia/core/models.py` / `core/adapters.py` — `AdapterRunRequest.network_name`
  is threaded through to `run_docker`.
- `app/aletheia/core/orchestrator.py` — `resume(..., wire_egress=True)` starts a
  `ProxySession` for each *wired* adapter, sets `proxy_url`/`network_name`, and appends the
  proxy's request log to the run's Phase 10 chain as `egress_request` events.
- Wired subset (3 of 49): `search_engines`, `ssl_tls`, `ip_intelligence`. The other 46 keep
  their previous behaviour; full coverage is deferred.
- `ci/egress_scenario.py` — new. Runs the whole shape on a real `--internal` network (a local
  origin plus the adapter image as the client) and asserts: the forwarded request returns 200
  and is logged; the real `search_engines` runner egresses through the proxy (`rc=0`); four
  `egress_request` events append to a chain that verifies valid; and the fail-closed property
  (no direct internet; no path once the proxy is stopped).
- `tests/test_egress_wiring.py` — 11 unit tests (argv builders, `ProxySession` with an
  injected runner, `run_docker` network selection, orchestrator wiring gating).
- `tests/test_docker_integration.py` — 3 new integration tests sharing one scenario run.
- `ci/capture_docker_integration.py` — records the 4 `phase12-egress-*` scenario checks.
- `docs/EGRESS_PROXY_CONTRACT.md` — new "Wiring pattern" section; status updated.
- Honest limitation: the proxy is wired into three adapters, not all 49. The scenario proves
  the pattern with the adapter image as the client and the real `search_engines` runner; per
  the standing rules it uses no live internet (the network is `--internal`).

## Phase 10 — hash-chained audit log (complete)

Implemented and CI-verified in commit `5037108`.

- `app/aletheia/core/chain.py` — new. A SHA-256 hash chain over each run's `AUDIT.jsonl`.
  Every entry carries `seq` (1-based), `prev_hash` (the previous entry's hash, or 64 zeroes
  for the genesis entry) and `hash` (SHA-256 of the canonical UTF-8 JSON with `hash`
  removed, keys sorted, compact separators). `append()` refuses to extend an invalid chain
  or a chain whose tip disagrees with the run `MANIFEST.json` anchor. `verify()` checks
  entry order, previous-hash links, entry hashes, the manifest `checkpoint_hash`, and the
  manifest `chain_tip` anchor.
- `app/aletheia/core/audit.py` — every `AuditLogger.log()` now appends through the chain.
- `app/aletheia/core/orchestrator.py` — publishes the verified `chain_tip` into the manifest
  on resume; a broken chain raises instead of being silently rewritten.
- `app/aletheia/core/checkpoint.py` — unchanged; the manifest already persists arbitrary
  keys, so `chain_tip` rides on the existing `CheckpointStore.save()` with its
  `checkpoint_hash`.
- `app/aletheia/phase2/service.py` — verifies the chain before any Phase 2 mutation.
- `app/aletheia/cli/main.py` — new `aletheia verify-chain <RUN_ID> [--data-dir …]` command.
- Tests: `tests/test_chain.py` (10 tests) plus `tests/test_phase2_service.py` chain-tip
  assertion. Tamper detection is covered (edited entry, removed final entry, stale
  manifest anchor, tampered checkpoint hash).

### Honest limitation (recorded, not softened)

The chain is **tamper-evident relative to a preserved manifest anchor**. It is **not** a
digital signature, it does not authenticate the manifest against an actor who can rewrite
both files together, and it is **not** a legal-admissibility guarantee. The README and
`docs/ADAPTER_CONTRACT.md` say the same thing.

## Phase 11 — egress proxy, standalone component (complete)

Implemented and CI-verified in commit `02ee887`; manifest status flipped in `255dc6d`.

- `app/aletheia/core/egress.py` — new control-plane module. `EgressLogEntry` /
  `parse_log_line` / `read_log` validate the proxy's JSONL schema; `TokenBucket` and
  `AdapterRateLimiter` implement a per-adapter token bucket with optional JSON persistence
  (atomic temp-file replace + `fsync`); `KillSwitch` reads an env flag or a flag file;
  `EgressProxy` builds the `docker run` argv and the `HTTP_PROXY`/`HTTPS_PROXY` environment
  for an adapter; `append_log_to_chain` writes each proxied request to the run's hash chain
  (`chain.append`, so a tampered run refuses the append).
- `docker/egress_proxy/proxy.py` — new. A standard-library `asyncio` forward proxy. Plain
  HTTP is forwarded from an absolute-form target; HTTPS `CONNECT` is tunnelled. The kill
  switch (403) and the token bucket (429) are applied before any upstream connection is
  opened; an upstream connect failure logs 502. `--health` prints exactly `ok` and opens no
  socket, so the container smoke runs under `--network none`. **Deviation, recorded:** the
  module is not literally ASGI — ASGI cannot carry `CONNECT` tunnels — so the forwarder is a
  stdlib `asyncio` server; the control-plane contract in `docs/EGRESS_PROXY_CONTRACT.md`
  is unchanged.
- `docker/egress_proxy/Dockerfile` — image `aletheia/egress-proxy:v1`, stdlib only, non-root
  `aletheia` user, no third-party package.
- `tests/test_egress.py` (31 tests) plus `tests/fixtures/egress_proxy_log.jsonl`; a
  container-health smoke in `tests/test_docker_integration.py`; capture case
  `phase11-egress-proxy` in `ci/capture_docker_integration.py`; a `docker/build.sh` target;
  a `PROJECT_MANIFEST.json` entry as an infrastructure component with `enabled_by_default:
  true` (invocation deliberately omits the substring `Docker` so the adapter set stays 49).
- `docs/EGRESS_PROXY_CONTRACT.md` — created (it was missing). It is the design/contract
  record for the component.

### Honest limitation (recorded, not softened)

The proxy log records what reached the proxy; it is **not** proof of what an adapter did
before that point, and the chain it feeds is **tamper-evident relative to a preserved run
manifest**, not a digital signature and not a legal-admissibility guarantee.

## Next action

**The authorized live self-audit has run** (run `39141366670`, target `username:frost2233`,
owner-asserted; every live-path defect found along the way is repaired and re-verified — see
the top CHANGELOG entry and the live-audit section above). What remains needs user decisions:

- **Gate 2 is satisfied for `frost2233` only.** Any other target — or a broader sweep — needs
  a fresh, explicit ownership assertion before a live run.
- **Gate 3** — free API keys as GitHub Secrets (`REDDIT_CLIENT_ID`/`SECRET`,
  `YOUTUBE_API_KEY`, `LEAKIX_API_KEY`, `GRAYHATWARFARE_TOKEN`) would turn three key-gated
  skips into live coverage. None are configured.
- Optional bookkeeping: promote the adapters exercised by the authorized run to
  `verified-live` using the run as copied evidence; and re-run the audit periodically as
  platform data changes.
- `transport_movement` and `darkweb_search` remain deferred on Gate 6 (registrations /
  written permission; no verifiable request contract).

## Known deferred issues

- **Egress coverage is proven by policy per adapter and by execution for four adapters.** Every
  `network_required=True` adapter is wired (checked against the registry), but the proxied path
  has only been exercised end to end for `search_engines`, `ssl_tls`, `ip_intelligence` and
  `crtsh`. An adapter whose client ignores the proxy variables fails closed rather than
  egressing unproxied; that failure mode is not demonstrated per adapter.
- No `verified-live` adapters in `PROJECT_MANIFEST.json`; every fixture is synthetic
  unless separately documented. The 2026-10-18 authorized run executed `sherlock`, `maigret`,
  `instaloader`, `social_username` and `leak_checkers` live without changing any
  `verification_status` — see the live-audit section.
- Score/confidence separation is incomplete; `--purpose` is not a required adapter field.
- `AUTONOMOUS_DIRECTIVE.md` and `AGENT_SETUP.md` live at the repo root and now reference
  `AUTONOMOUS_DIRECTIVE.md` correctly; the four stale `docs/AUTONOMOUS_DIRECTIVE.md` paths
  were fixed in the directive commit following `f0352a4`.
- Multi-seed trees share one graph/audit chain/run directory, and the cross-seed boost is a
  documented heuristic prior, not calibrated output (`docs/MULTI_SEED.md`).
- Context filters are enforced only where a comparable attribute exists, and no adapter
  consumes them beyond receiving them on the request.
- Jurisdiction warnings are heuristic and informational; expected false positives and false
  negatives (`docs/JURISDICTION_WARNINGS.md`).
- **Point-in-time documents deliberately left unedited.** `audit/CLAIMS_VS_VERIFIED_AUDIT.md`
  keeps its Step 3 rows (with a superseded-in-part banner) rather than being rewritten, and
  `aletheia_step3_CI_READY.md` still calls the egress proxy non-existent (superseded by Phase
  11). They record the state at their moment of writing; this handoff supersedes both.
- The audit trail of unverified claims in `RESUME_STATE.json` before 2026-10-14 should be
  treated as reconstructed, not primary evidence.

## Open gates

- **Gate 2** — user-owned target required before any live investigation. Satisfied on
  2026-10-18 for `username:frost2233` (owner assertion recorded verbatim in the run
  manifest); any other target re-opens the gate.
- **Gate 3** — verify API keys and cost before a phase depends on them. Still open; no keys
  are configured, so `reddit-api`, `youtube-api` and `leak_checkers` skip by design. The
  grouped free-registration master list is `docs/USER_ACTIONS.md` (see also
  `docs/SOURCE_COMPLETENESS.md` §C).
- **Gate 5** — evidence lines must be copied from a downloaded artifact, never typed.
- **Gate 6** — `transport_movement` and `darkweb_search` build in the autonomous campaign
  (transport with recorded skip paths; dark web behind container-level Tor); live coverage
  for each remains gated on owner registrations / written permission and Tor setup —
  grouped in `docs/USER_ACTIONS.md`.
- **Gate 6 (MinIO server)** — deferred pending a usable image or endpoint: `minio/minio`
  returns 404 on Docker Hub and `quay.io/minio/minio` refuses anonymous pulls, so the S3 code
  path is verified against `adobe/s3mock:5.2.3` instead.

## Briefing corrections (standing rule 10)

- The session brief said Phase 10 was uncommitted, left one failing test double, and that
  the local suite was 518 passed / 50 skipped (568 total). All three were stale: Phase 10
  was already committed as `5037108` and pushed; the test double in `tests/test_chain.py`
  already creates the per-adapter workspace (matching `Adapter.run`); and the real local
  count is 520 passed / 50 skipped = 570, matching CI.
