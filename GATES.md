# Project Gates

Last reviewed: 2026-10-11

## Open gates

None currently awaiting a user decision.

## Resolved gates

- **Gate 1 — LeakCheck classification:** The project owner selected “Exclude it” on 2026-10-11. LeakCheck is excluded from Phase 5b, is absent from the active Phase 5b proposal registry, and has no implementation.
- **Phase 5b scoped-source review:** Hudson Rock, DarkNyx, and osint-darkweb-pkg were excluded on 2026-10-11 because their documented endpoints/call paths did not establish a stable Tier 1–2-only scope. Evidence and precise constraints are in `docs/NOT_INTEGRATED.md`.

## Checks to perform when the task reaches them

- **Gate 3 — API keys and cost:** Before a phase depends on Shodan, HIBP, Reddit, YouTube, OpenCorporates, or another key-protected service, verify access and cost. Ask for user action if a required free-registration key is not available. Do not add a paid default dependency.
- **Gate 4 — tier uncertainty:** Stop before registering or implementing any candidate whose data source, response fields, or method may cross the Tier 4/5 hard floor. Record the exact uncertainty and ask the project owner.
- **Gate 2 — live target:** Before the authorized live-investigation phase, verify that the target is user-owned and explicitly supplied for that run. Do not use an unrelated target.
