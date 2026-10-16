# Adapter contract

Each adapter provides:

- `name`
- `license`
- `input_types`
- `output_types`
- `legal_notes`
- `rate_limit`
- `invocation`
- `version_pin`
- `upstream`
- `network_required`
- `docker_image`

Execution is always through `docker run --rm` in Phase 1. The adapter parses only tool-produced artifacts/stdout and converts them into typed `Finding` objects with `Provenance`.

A claim is not considered system-confirmed merely because a tool reports it. Cross-tool entity resolution and re-verification belong to Phase 2.

## Audit chain

Each line in a run's `AUDIT.jsonl` contains the event fields plus:

- `seq`: one-based entry number.
- `prev_hash`: SHA-256 of the previous entry, or 64 zeroes for the genesis entry.
- `hash`: SHA-256 of the canonical UTF-8 JSON entry with `hash` omitted, keys sorted, and compact separators. The hashed entry includes `seq` and `prev_hash`.

The run's `MANIFEST.json` records the final `chain_tip`. `aletheia verify-chain <RUN_ID>` checks entry order, previous-hash links, event hashes, the checkpoint hash, and the manifest anchor. A chain detects edits or removals relative to a preserved manifest; it does not authenticate a manifest against an actor able to rewrite both files, and it is not itself a legal-admissibility guarantee.
