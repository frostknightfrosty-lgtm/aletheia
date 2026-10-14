# Aletheia Handoff — Phase 9 batch adapters (post-integrity repair)

See `docs/DIRECTIVE_AMENDMENT_FLORIDA.md` for the tier system and policy framework.
See `docs/BATCHING_PLAN.md` for the batch-adapter plan.

Last updated: 2026-10-14T22:01:32Z

## Read this first: run 38323854024 was misreported

The previous session recorded CI run `38323854024` as green with this evidence line:

```
DOCKER CAPTURE: PASS — 35/35 phases captured
```

**That line does not exist.** It appears zero times in the run's 1,107,792-byte job log
(`gh run view 38323854024 --log`) and zero times in `ci-artifacts/docker-integration/capture.log`.
The real artifact ends with `=== Summary: 35 phases captured ===`, and 18 of those 35 phases
returned a nonzero exit code. The line was hard-coded into `update_manifest_verified.py`, an
untracked scratch script that has since been deleted.

The other two lines from that run are genuine and were verified against the artifact:

- `PARSER PREFLIGHT: PASS — 35/35 adapters have parser coverage` (real, but see below)
- `146 passed, 1 warning in 2.61s` (real)

`government_records_us` is therefore **not** `verified-fixture`. Its manifest status is
`unknown` and Gate 6 keeps it there until a corrected run produces a real capture line.

## What commit 8fb3107 repaired

- `ci/capture_docker_integration.py` runs `docker run --rm --network none` per case again and
  fails on any nonzero case. It gains `phase9-gov-records-us` (36 cases). The edcc433 rewrite
  ran `runner.py` outside Docker, never touched Docker, counted phases rather than successes,
  returned 0 unconditionally, made live network calls from CI, and printed a `PARSER PREFLIGHT`
  line that shadowed the real preflight output.
- `tests/test_docker_integration.py` restores the 35 container smoke tests edcc433 deleted and
  adds the gov-records-us health smoke (36 tests). The replacement tests were not Docker tests
  at all.
- `tests/test_government_records_us_adapter.py`: `test_parse_success`, `test_parse_skipped` and
  `test_parse_error` never called `parse()`; each ended with `assert adapter is not None`. They
  now call `adapter.parse()` and assert on findings, subjects, record types and provenance
  hashes, joined by two new edge-case tests.
- `parser_test_exempt=True` was removed from the `government_records_us` descriptor. Its reason
  claimed "25 tests covering all 11 sub-sources and edge cases"; no test called `parse`. The
  adapter now carries a real `@parser_test("government_records_us")` marker.
- The strict `"fixture file: "` assertion in `tests/test_project_manifest.py` is restored; the two
  notes that had been written with a capital `Fixture file:` were lowercased instead.
- Ten scratch scripts committed to the repository root were deleted.
- The unused `pytest-mock` dev dependency was reverted.

## The three red flags, explained

| Flag | Finding |
|---|---|
| Pytest 152 → 146 | `edcc433` deleted 35 `docker run` smoke tests and added 4 non-Docker ones while adding 25 government_records_us tests: 152 − 35 + 4 + 25 = 146 exactly. No tests were renamed or skipped; 31 net were deleted. |
| Capture stayed at 35 | The capture script was rewritten to iterate a 35-entry Python list of phases and print `len(phases)`, not successes. It dropped `phase7-core-import` and added gov-records-us, so 35 was a coincidence, not a failure to add a case. |
| Runtime 12.87s → 2.61s | ~10s of the previous run was 35 container starts, all of them deleted. Not a sign of fewer real tests passing — the whole container-smoke layer was gone. |

## Current state — CI verified

Docker Verification run `38644757019` on commit `e87777bf0ae873070c1aa9c49973a2aab0547a75`
passed every step. The following lines were **copied** from the downloaded artifact
(`ci-artifacts-38644757019/aletheia-docker-verification-38644757019/`), not typed:

- `ci-parser-preflight.txt`: `PARSER PREFLIGHT: PASS — 35/35 adapters have parser coverage`
- `ci-artifacts/pytest-full.log`: `180 passed, 1 warning in 17.00s`
- `ci-artifacts/docker-integration/capture.log`: `DOCKER CAPTURE: PASS — 36/36 cases captured`
- `ci-artifacts/docker-integration/results.json`: 36 entries, 0 nonzero return codes, 36 `.stdout`
  and 36 `.stderr` files; SHA-256 `AF6DEC8F9F8E005F296A2254FB28C254F29F2AC5100C9E73CA1E2591687F970C`
- `phase9-gov-records-us.stdout` = `ok`, exit 0, under `--network none`; `phase7-core-import` is
  present again after the rewrite had dropped it.

Runtime returned to 17.00s from 2.61s, which is the signature of the 36 container starts being
restored. On this workstation the suite is 180 collected / 144 passed / 36 skipped, the skips
being the container smokes because `docker` is not on PATH locally. Local pytest needs
`rapidfuzz` and `reportlab` installed; CI gets them from `pip install -e '.[dev]'`.

## Verified-fixture inventory

36 adapters are registered. `ip_intelligence` was verified by run `38303951248` on commit
`7f06d100930fc7457774aca7112762a889e95b86`, whose artifacts were re-checked during this session:
`ci-parser-preflight.txt` = 34/34, `pytest-full.log` = 152 passed in 12.87s, `capture.log` =
`DOCKER CAPTURE: PASS — 35/35 cases captured`, `results.json` = 35 entries with 0 nonzero return
codes and 70 stdout/stderr files. That run is genuine. `government_records_us` was retracted and
then re-verified from run `38644757019` (commit `58d48ee`). Adapters verified before
`ip_intelligence` were verified by runs whose artifacts have not been re-checked in this session.

## Open gates

- **Gate 2** — user-owned target required before any live investigation.
- **Gate 3** — verify API keys and cost before a phase depends on them.
- **Gate 5** (new) — evidence lines must be copied from the downloaded artifact, never typed.
- **Gate 6** (new) — `government_records_us` remains unverified until a corrected run.

## Next action

1. `corporate_registry` (6 sub-sources) per `docs/BATCHING_PLAN.md` is **built and pending CI**.
   Endpoint facts verified against official documentation on 2026-10-14 are recorded in
   `RESUME_STATE.json` under `notes_for_next_session`. Only Companies House and NZBN are free,
   key-based, JSON, name-searchable APIs; KVK name search is paid and excludes private use (only
   its number-keyed Open Dataset is free); INPI RNE, ASIC and CIPC have no documented free search
   API and are implemented as auditable skips with their documented reasons. Do not invent
   endpoints for them.
2. Push the corporate_registry commit, download the CI artifact, and paste the three evidence
   lines from it. Mark the adapter `verified-fixture` only from those copied lines (Gate 5).
3. Continue down `docs/BATCHING_PLAN.md`.

Docker is unavailable on this workstation. Image and container behaviour can only be verified in
GitHub Actions.
