# Step 1 — Parser Coverage Checkpoint

## Result

- Tagged Phase 7 adapter inventory: **33 adapters**.
- Parser coverage pre-flight: **33/33 PASS**.
- Local pytest: **70 passed, 34 skipped**.
- The 34 skips are still Docker integration tests only; no Docker capability is claimed as live-verified.

## Changes

1. Added parser fixture coverage for `assetfinder`, `dnsrecon`, and `fierce`.
2. Added `parser_test` markers to all 33 adapter parser tests.
3. Added `ci/check_parser_coverage.py`, a fail-fast inventory-vs-tests checker.
4. Added explicit `parser_test_exempt` and `parser_test_exempt_reason` fields to `AdapterDescriptor`. No current adapter uses an exemption.
5. Added the parser coverage gate to `.github/workflows/docker-verification.yml` before Docker verification.

## What the gate checks

- Every adapter in `phase7_adapters()` has at least one `parser_test(...)` marker, or an explicit exemption with a non-empty reason.
- Marked tests must contain an actual `.parse()` call.
- Unknown adapter names fail the gate.
- Duplicate parser coverage declarations fail the gate.

## Local evidence

```text
PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage
70 passed, 34 skipped
workflow YAML parsed successfully
```

## Boundary

This checkpoint does **not** promote any adapter to `verified-live`. The 34 Docker tests remain pending until Docker-capable CI/local execution produces raw container output.
