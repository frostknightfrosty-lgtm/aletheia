# Changelog

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
