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

## Current local state (not CI-verified)

- `PARSER PREFLIGHT: PASS — 35/35 adapters have parser coverage` (real marker, no exemption).
- 180 tests collected, 144 passed, 36 skipped. The 36 skips are `tests/test_docker_integration.py`
  skipping because this workstation has no Docker CLI; CI runs them against real containers.
- Local pytest needs `rapidfuzz` and `reportlab` installed; CI gets them from `pip install -e '.[dev]'`.

## Verified-fixture inventory

35 adapters are registered. `ip_intelligence` was verified by run `38303951248` on commit
`7f06d100930fc7457774aca7112762a889e95b86`, whose artifacts were re-checked during this session:
`ci-parser-preflight.txt` = 34/34, `pytest-full.log` = 152 passed in 12.87s, `capture.log` =
`DOCKER CAPTURE: PASS — 35/35 cases captured`, `results.json` = 35 entries with 0 nonzero return
codes and 70 stdout/stderr files. That run is genuine. `government_records_us` is the only
adapter whose verification was retracted; every adapter before it was verified by runs whose
artifacts have not been re-checked in this session.

## Open gates

- **Gate 2** — user-owned target required before any live investigation.
- **Gate 3** — verify API keys and cost before a phase depends on them.
- **Gate 5** (new) — evidence lines must be copied from the downloaded artifact, never typed.
- **Gate 6** (new) — `government_records_us` remains unverified until a corrected run.

## Next action

1. Confirm the corrected Docker CI run is genuinely green: parser 35/35; test count ≈180; a real
   `DOCKER CAPTURE: ... — 36/36 cases captured` line with `results.json` showing 0 nonzero.
2. Re-mark `government_records_us` as `verified-fixture` using the copied lines, in its own commit.
3. Implement `corporate_registry` (6 sub-sources) per `docs/BATCHING_PLAN.md`.

Docker is unavailable on this workstation. Image and container behaviour can only be verified in
GitHub Actions.
