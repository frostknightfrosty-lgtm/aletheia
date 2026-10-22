# Project Gates

Last reviewed: 2026-10-22

## Open gates

- **Gate 5 — evidence must be copied, never typed:** No adapter may be marked `verified-fixture` from a predicted, remembered, or hand-written evidence line. The three lines must be copied from the downloaded CI artifact for the exact run being cited. Opened 2026-10-14 after run `38323854024` was recorded with `DOCKER CAPTURE: PASS — 35/35 phases captured`, a line that does not exist anywhere in that run's log or artifacts and was hard-coded in `update_manifest_verified.py`.
- **Gate 6 — transport_movement — deferred pending user action. Requires: (1) registration at BarentsWatch, Network Rail, National Rail, Deutsche Bahn; (2) written permission from OpenSky for REST integration. Resume when user chooses to pursue.** This is a deferral, not an exclusion.
- **Gate 6 — darkweb_search — deferred pending technical source verification.** No sub-source has a documented, verifiable request contract suitable for the composite pattern. `Ahmia` has a public portal but no machine API; `Piano/darknet-crawler` requires a Tor SOCKS proxy and container-level Tor setup; `TorBot` is a page crawler, not a keyword-search endpoint; `Intelligence X` requires a registered `X-Key`; `OnionSearch` is a multi-engine scraper with no stable documented scope. Under the Operator-Driven Model, ToS hostility is not a project-level legal blocker; the operator assumes that risk. Revisit when a Tor-based search tool with a stable API is identified or a standardized container-level Tor setup is adopted.

- ~~**Gate 6 — government_records_us is unverified:**~~ **RESOLVED 2026-10-14.** Docker Verification run `38644757019` on commit `e87777bf0ae873070c1aa9c49973a2aab0547a75` produced `DOCKER CAPTURE: PASS — 36/36 cases captured` with `results.json` holding 36 entries and 0 nonzero return codes. `government_records_us` is `verified-fixture` again from commit `58d48ee`, using only lines copied from the downloaded artifact.

- **Gate 7 — `corporate_financial_public_records` cannot be built as planned:** Opened and closed 2026-10-15 as a documented exclusion. Four of its five sub-sources already live in `government_records_us`; the fifth, FollowTheMoney, publishes no request-parameter contract for name-based queries (its official 80-page API PDF documents response tags only and contains zero occurrences of `api.followthemoney.org`, `APIKey`, `mode=` or `entity.php`), and its parent OpenSecrets states that "as of April 15, 2025, our API offerings have been discontinued", offering only a commercial route that standing rule 4 forbids. No adapter was built. Re-open only if the vendor publishes a documented request contract or a free access route. See `docs/NOT_INTEGRATED.md`.

None of the remaining gates block local adapter implementation.

## Pre-7f06d10 verification audit (2026-10-15)

**Cleared.** All 10 successful runs on commits before `7f06d10` were re-examined by downloading their
artifacts: `38270478612`, `38272314026`, `38273505822`, `38274729412`, `38275780719`,
`38275780791`, `38290727897`, `38291743287`, `38292770527`, `38293763683`. For every run,
`ci-parser-preflight.txt`, the last line of `ci-artifacts/pytest-full.log`, the first line of
`ci-artifacts/docker-integration/capture.log`, and `results.json` agree with each other: the capture
count equals the number of `results.json` entries, every entry returns 0, and the stdout/stderr file
counts match the entry count. Every `capture.log` begins with a real `DOCKER CAPTURE: PASS — N/N cases
captured` line. **No fabricated evidence line was found in any of them.** The fabrication in run
`38323854024` was isolated, not systematic.

**Citation gap found and closed.** 29 of the 36 `verified-fixture` adapters cited no run at all — their
notes claimed only "Fixture parser coverage passes" while asserting `verified-fixture`. Every one of
those 29 has a passing capture case in run `38293763683` (commit
`d784850ed5d869393c63e180cfb05035c070513e`), so the evidence was real but undocumented. Commit
`70f4828` added the run, commit, copied run-level evidence lines, and the per-adapter case name and
return code to each of the 29 notes. No `verification_status` changed and no assertion was weakened.

**Standing rule going forward:** every `verified-fixture` adapter must cite a run whose artifact has
been read. A new adapter starts at `unverified-fixture` and moves to `verified-fixture` only from
copied artifact lines.
 Before any XposedOrNot live lookup, obtain an email address the user owns or is explicitly authorized to investigate.

## Resolved gates

- **Gate 1 — LeakCheck classification:** The 2026-10-11 exclusion decision was superseded by the owner on 2026-10-12. LeakCheck is permitted by the current project policy but remains unimplemented; no source query was made.
- **Phase 5b scoped-source review (historical):** The 2026-10-11 source review recorded exclusions for Hudson Rock, DarkNyx, osint-darkweb-pkg, Blackbird, and Lullar under the then-current policy. On 2026-10-12, the owner changed the project policy for Hudson Rock, Blackbird, and Lullar; those sources are permitted but not integrated. DarkNyx and osint-darkweb-pkg remain unimplemented. Under the 2026-10-22 Operator-Driven Model, ToS/source-review concerns are risk notes, not project-level legal exclusions. The review does not revise source-review evidence or authorize new implementation by itself. See `docs/NOT_INTEGRATED.md`.
- **ONYPHE:** The owner selected “Exclude ONYPHE” on 2026-10-11 after review of Free View terms limiting the free license to individual use, prohibiting commercial reuse, and distinguishing own-account use from paid client/business use. Under the 2026-10-22 Operator-Driven Model, ONYPHE is permitted; the Free View terms are a risk the operator assumes. It remains unimplemented, and no adapter was built.
- **Phase 5c source scope:** Gravatar and RDAP are implemented with public profile and exact registration-data scopes. RDAP is `verified-fixture` from Docker Verification run 38270478612; no live RDAP lookup occurred. Mr.Holmes, IVRE, urlscan, ThreatCluster, and Social Analyzer remain unimplemented; the Operator-Driven Model does not treat source/ToS review as a legal ban. See `docs/PHASE_5C_REGISTRY.md` and `docs/NOT_INTEGRATED.md`.
- **Operator-Driven Model adopted:** On 2026-10-22, the owner removed the Tier 5 hard floor and adopted SpiderFoot parity. Tiers are descriptive; the code is not a legal gatekeeper. All passive OSINT sources, including leak indexes and dark-web scrapers, are permitted; the operator assumes full legal responsibility. Active network intrusion and malware deployment are not implemented. See `docs/OPERATOR_DRIVEN_MODEL.md`.
- **Tier 5 hard floor removed by owner mandate on 2026-10-22. Aletheia shifted to Operator-Driven Model.**

## Checks to perform when the task reaches them

- **Gate 3 — API keys and cost:** Before a phase depends on Shodan, HIBP, YouTube, OpenCorporates, or another key-protected service, verify access and cost. Ask for user action if a required free-registration key is not available. Do not add a paid default dependency.
- **Gate 2 — live target:** Before the authorized live-investigation phase, verify that the target is user-owned and explicitly supplied for that run. Do not use an unrelated target.

## Paused work note (2026-10-16)

The user paused work during preliminary `darkweb_search` source review. No new numbered gate was opened and no source was implemented. Resume from `HANDOFF.md`; distinguish Piano's published, single-engine search invocation from TorBot's page crawling and Intelligence X's registered-key API. Under the Operator-Driven Model, Ahmia's Terms of Service are a risk the operator assumes; the remaining blocker is technical (no machine API), not legal.
