# Project Gates

Last reviewed: 2026-10-11

## Open gates

None currently blocking source review or adapter implementation. Before any XposedOrNot live lookup, obtain an email address the user owns or is explicitly authorized to investigate.

## Resolved gates

- **Gate 1 — LeakCheck classification:** The project owner selected “Exclude it” on 2026-10-11. LeakCheck is excluded from Phase 5b, is absent from the active Phase 5b proposal registry, and has no implementation.
- **Phase 5b scoped-source review:** The owner required exact, enforceable Tier 1–2 scopes for Hudson Rock, DarkNyx, and osint-darkweb-pkg. Review found Hudson Rock's username endpoint returns credential objects, DarkNyx has no documented public metadata-only API and prohibits scraping, and the package cannot restrict its query to Ahmia/Torch/OnionLand. All three were excluded on 2026-10-11. Blackbird was also excluded for no declared license; Lullar for no documented machine-readable interface. Evidence is in `docs/NOT_INTEGRATED.md`.

## Checks to perform when the task reaches them

- **Gate 3 — API keys and cost:** Before a phase depends on Shodan, HIBP, Reddit, YouTube, OpenCorporates, or another key-protected service, verify access and cost. Ask for user action if a required free-registration key is not available. Do not add a paid default dependency.
- **Gate 4 — tier uncertainty:** Stop before registering or implementing any candidate whose data source, response fields, or method may cross the Tier 4/5 hard floor. Record the exact uncertainty and ask the project owner.
- **Gate 2 — live target:** Before the authorized live-investigation phase, verify that the target is user-owned and explicitly supplied for that run. Do not use an unrelated target.
