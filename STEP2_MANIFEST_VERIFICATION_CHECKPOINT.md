# Aletheia Step 2 Checkpoint — Manifest Verification Status

## Scope
Step 2 only: replace the legacy verification bookkeeping field with `last_audited`, add required `verification_status`, and enforce the six-value evidence schema in the repository manifest loader.

No adapter code, parser code, CI workflow, or HANDOFF.md standing-rule changes were made in Step 2.

## Verification status values

The only permitted values are:

- `verified-live`
- `verified-fixture`
- `verified-source-read`
- `asserted`
- `unknown`
- `blocked`

The loader rejects the legacy fields `verified`, `verified_date`, and `last_verified` rather than aliasing them.

## Current distribution

- `verified-live`: 0
- `verified-fixture`: 33
- `verified-source-read`: 2
- `asserted`: 0
- `unknown`: 0
- `blocked`: 0

There are 35 manifest entries: 33 adapters plus two internal dependencies (`rapidfuzz` and `reportlab`). The 33 adapters are `verified-fixture` because Step 1 established parser-test coverage for all 33. This does not imply a live container run. The two internal dependencies are `verified-source-read` because their upstream package/version documentation was previously reviewed; they are not adapter parsers.

## Validation

`77 passed, 34 skipped` locally. The 34 skips remain Docker integration tests and are unchanged by Step 2.

The manifest loader is strict: missing required fields, invalid statuses, empty notes on `asserted`/`unknown`, legacy verification fields, malformed audit timestamps, and missing repository-relative evidence for `verified-live` all fail loudly.
