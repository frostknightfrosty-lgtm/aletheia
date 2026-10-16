# Aletheia Handoff — Phase 9 batch adapters (post-audit)

See `AUTONOMOUS_DIRECTIVE.md` for standing rules and `docs/BATCHING_PLAN.md` for the adapter plan.

## User-requested pause — darkweb_search source review (2026-10-16)

Current local HEAD at pause: `0f1876e4b46c73ececa9eef51d1a9403ae4f387b` (`state: record social_username verification in run 38901112098`). The worktree was clean before this handoff update. No adapter implementation or other project-code edits were made during the resumed turn. The user explicitly asked to pause because context was nearly exhausted.

The state-only push triggered Docker Verification run `38902790400`, URL https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38902790400. Last checked status was `in_progress`; do not report it green. On resume, check its status and, if complete, download/read its artifact before citing it.

The next unfinished eligible plan row is `darkweb_search`; `transport_movement` remains deferred under Gate 6 and is not excluded. Preliminary source review found:

- Piano / `darknet-crawler` 0.1.2 is published on PyPI and documents a search CLI with engine allowlisting and Tor mode. Its official package page says it queries existing indexes and that broad arbitrary onion spidering is opt-in. The PyPI sdist was downloaded to the Windows temp directory and its SHA-256 matched the PyPI value `3e766ccddd2007303ed49f2efefc6eb00716993e71ae2c9acd0d3fc7446c7eed`. The published package source contains an `ahmia_onion` engine at `http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search`; Ahmia's own About page confirms that onion address. The narrow candidate is one Piano query restricted to that engine, `--mode tor`, with no spider/fetch/enrichment.
- Ahmia's current Terms of Service explicitly prohibit scraping or replicating the service without permission. The project’s Florida directive classifies public ToS-hostile scraping as allowed/Tier 2; this conflict must be recorded clearly if that source is implemented. No query was made.
- OnionSearch's official README describes a scraper across 16 engines; its upstream source includes several entries marked offline and hard-coded service endpoints. The current review did not establish a reliable, current multi-engine scope.
- TorBot's current official CLI takes a URL and crawls pages; it is not a keyword-search endpoint.
- Intelligence X's official SDK/API docs require a registered API key in `X-Key`; it is not keyless.

No final sub-source selection was made and no code was written. Next action: finish the above CI-run check, then continue the `darkweb_search` source review with only a documented, tightly selected, keyless index if usable; otherwise record the exact source drops and move to the next non-blocked plan row. Do not claim live-source verification from the CI health smoke.

Last updated: 2026-10-17T06:05:00Z

## Read this first: the 38323854024 fabrication was isolated

Run `38323854024` was recorded with the evidence line `DOCKER CAPTURE: PASS — 35/35 phases captured`.
That line exists nowhere in the run's job log or artifacts; it was hard-coded into a scratch script.
It was retracted, the deleted Docker verification was restored, and `government_records_us` was
re-verified from run `38644757019` (commit `58d48ee`).

**A full audit on 2026-10-15 confirmed the fabrication did not spread.** All 10 successful runs on
commits before `7f06d10` were re-examined from downloaded artifacts:

`38270478612`, `38272314026`, `38273505822`, `38274729412`, `38275780719`, `38275780791`,
`38290727897`, `38291743287`, `38292770527`, `38293763683`.

For every one of them the parser preflight file, the pytest tail, the first line of `capture.log`,
and `results.json` agree with each other: the capture count equals the number of `results.json`
entries, every entry returns 0, and the stdout/stderr file counts equal the entry count. Every
`capture.log` begins with a real `DOCKER CAPTURE: PASS — N/N cases captured` line. **No fabricated
evidence line was found.** The failure was one session, not a pattern.

## The citation gap the audit did find

29 of the 36 `verified-fixture` adapters cited **no run at all** — their notes said only
"Fixture parser coverage passes" while asserting `verified-fixture`. Every one of those 29 has a
passing capture case in run `38293763683` (commit `d784850ed5d869393c63e180cfb05035c070513e`), so
the evidence was real but undocumented. Commit `70f4828` added the run, commit, copied run-level
evidence lines, and each adapter's own case name and return code to all 29 notes. No
`verification_status` changed.

The seven adapters that already cited a run all pass too. Five cite full lines that match their
artifacts exactly (`gravatar`, `rdap`, `ip_intelligence`, `government_records_us`,
`corporate_registry`); two cite a run whose capture case returns 0 (`xposedornot`, `phoneinfoga`).

## Current CI-verified state

- **44 adapters registered, all `verified-fixture`; 45 Docker integration cases.**
- `code_search` verified by run `38811234205` on `f59458f`: parser `43/43`, `484 passed, 1 warning in 20.60s`, capture `44/44`.
- `search_engines` verified by run `38813318506` on `316172b`: parser `44/44`, `518 passed, 1 warning in 15.38s`, capture `45/45`.
- The count-drift burden is fixed: a new adapter should now require **no** edits to any other test file. If one is needed, treat it as a regression.
- Local at handoff: 473 passed, 45 skipped (the container smokes; `docker` is not on PATH here).
- **Reusable cross-check:** local (passed + skipped) equals CI passed exactly, because CI runs the container smokes that skip locally. It held three times this session: 412+43=455, 440+44=484, 473+45=518. If it breaks, a test was skipped or deleted.
## Plan divergence you must resolve before the next composites

`docs/BATCHING_PLAN.md` lists 21 composites, but two already-implemented adapters absorbed part of
the plan:

- `ip_intelligence` merged the plan's `ip_intelligence_geo`, `ip_intelligence_reputation` and
  `ip_intelligence_threat_exposure` rows into one 15-sub-source adapter.
- `government_records_us` already implements seven sub-sources the plan assigns elsewhere:
  `finra-brokercheck`, `fed-enforcement`, `occ-enforcement` (planned for
  `sanctions_enforcement_watchlists`) and `fdic-bankfind`, `lda`, `usaspending`, `sam-gov`
  (planned for `corporate_financial_public_records`).

So the two "next" composites have far less new work than the plan implies:
`sanctions_enforcement_watchlists` needs only UK Sanctions List, Swiss SECO and EU Consolidated
Sanctions; `corporate_financial_public_records` needs only FollowTheMoney. Implementing the plan
rows literally would query the same endpoints from two adapters. This adapter is scoped to the
missing sub-sources only, and its manifest note says so.

## Deferred issues

- No verified-live adapters; every fixture is synthetic unless separately documented.
- No implemented egress proxy. Graph/checkpoint storage is file-backed JSON.
- Audit log has no verifiable hash chain or chain-of-custody command.
- Score/confidence separation is incomplete; `--purpose` is not a required adapter field.
- `docs/AUTONOMOUS_DIRECTIVE.md` does not exist; the directive lives at repo root as
  `AUTONOMOUS_DIRECTIVE.md`, and `AGENT_SETUP.md` is also at the repo root. Both files reference
  `docs/AUTONOMOUS_DIRECTIVE.md`. Worth fixing or documenting.
- The audit trail of unverified claims in `RESUME_STATE.json` before 2026-10-14 should be treated
  as reconstructed, not as primary evidence.

## Open gates

- **Gate 2** — user-owned target required before any live investigation.
- **Gate 3** — verify API keys and cost before a phase depends on them.
- **Gate 5** — evidence lines must be copied from a downloaded artifact, never typed.
- Gate 6 — RESOLVED 2026-10-14: `government_records_us` re-verified from run `38644757019`.

## Next action

1. Pick the next composite from `docs/BATCHING_PLAN.md`. Still unimplemented: `geolocation_image`, `transport_movement`,
   `transport_asset_registry`, `leak_checkers`, `research_discovery`, `social_username`, `social_profile`, `darkweb_search`,
   `technical_surface_search`.
2. Diff its sub-source list against `PROJECT_MANIFEST.json` first, then verify every endpoint against vendor docs before
   writing code. `technical_surface_search` must NOT re-implement `checkdmarc` or `scan-mx`, which live in `email_auth`.
3. One composite per commit and per CI run; mark `verified-fixture` only from artifact-copied lines (Gate 5).
4. Preferred build shape: pre-verify the endpoints yourself, then hand one composite to a subagent forbidden from
   touching `PROJECT_MANIFEST.json` or `tests/test_project_manifest.py`; verify its output independently, add the manifest
   entry, commit, push, wait for CI, and copy the evidence.
5. `corporate_financial_public_records` stays **excluded** (Gate 7); see `docs/NOT_INTEGRATED.md`.
Docker is unavailable on this workstation. Image and container behaviour can only be verified in
GitHub Actions.
