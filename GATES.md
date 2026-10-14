# Project Gates

Last reviewed: 2026-10-14

## Open gates

- **Gate 5 — evidence must be copied, never typed:** No adapter may be marked `verified-fixture` from a predicted, remembered, or hand-written evidence line. The three lines must be copied from the downloaded CI artifact for the exact run being cited. Opened 2026-10-14 after run `38323854024` was recorded with `DOCKER CAPTURE: PASS — 35/35 phases captured`, a line that does not exist anywhere in that run's log or artifacts and was hard-coded in `update_manifest_verified.py`.
- ~~**Gate 6 — government_records_us is unverified:**~~ **RESOLVED 2026-10-14.** Docker Verification run `38644757019` on commit `e87777bf0ae873070c1aa9c49973a2aab0547a75` produced `DOCKER CAPTURE: PASS — 36/36 cases captured` with `results.json` holding 36 entries and 0 nonzero return codes. `government_records_us` is `verified-fixture` again from commit `58d48ee`, using only lines copied from the downloaded artifact.

None of the remaining gates block local adapter implementation. Before any XposedOrNot live lookup, obtain an email address the user owns or is explicitly authorized to investigate.

## Resolved gates

- **Gate 1 — LeakCheck classification:** The 2026-10-11 exclusion decision was superseded by the owner on 2026-10-12. LeakCheck is permitted by the current project policy but remains unimplemented; no source query was made.
- **Phase 5b scoped-source review (historical):** The 2026-10-11 source review recorded exclusions for Hudson Rock, DarkNyx, osint-darkweb-pkg, Blackbird, and Lullar under the then-current policy. On 2026-10-12, the owner changed the project policy for Hudson Rock, Blackbird, and Lullar; those sources are permitted but not integrated. DarkNyx and osint-darkweb-pkg remain excluded. The policy change does not revise source-review evidence or authorize new implementation by itself. See `docs/NOT_INTEGRATED.md`.
- **ONYPHE:** The owner selected “Exclude ONYPHE” on 2026-10-11 after review of Free View terms limiting the free license to individual use, prohibiting commercial reuse, and distinguishing own-account use from paid client/business use. No adapter will be implemented.
- **Phase 5c source scope:** Gravatar and RDAP are implemented with public profile and exact registration-data scopes. RDAP is `verified-fixture` from Docker Verification run 38270478612; no live RDAP lookup occurred. Mr.Holmes, IVRE, urlscan, ThreatCluster, and Social Analyzer remain excluded after source/scope review. See `docs/PHASE_5C_REGISTRY.md` and `docs/NOT_INTEGRATED.md`.
- **Florida policy amendment:** On 2026-10-12, the owner replaced the prior grey posture and tier defaults with the project framework in `docs/DIRECTIVE_AMENDMENT_FLORIDA.md`. LeakCheck, LeakRadar, OsintCat, OathNet, Blackbird, Lullar, and Hudson Rock are permitted but not thereby integrated. ONYPHE remains excluded by owner decision. The four-category Tier 5 list is project policy, not a complete statement of applicable law.

## Checks to perform when the task reaches them

- **Gate 3 — API keys and cost:** Before a phase depends on Shodan, HIBP, Reddit, YouTube, OpenCorporates, or another key-protected service, verify access and cost. Ask for user action if a required free-registration key is not available. Do not add a paid default dependency.
- **Gate 4 — tier uncertainty:** Stop before implementing a candidate whose source, response fields, or method may cross one of the four Tier 5 categories in `docs/DIRECTIVE_AMENDMENT_FLORIDA.md`. Do not re-ask policy calls already recorded there.
- **Gate 2 — live target:** Before the authorized live-investigation phase, verify that the target is user-owned and explicitly supplied for that run. Do not use an unrelated target.
