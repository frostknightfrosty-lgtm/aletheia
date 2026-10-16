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

## Calibrated vs uncalibrated scores

Every adapter attaches a `Provenance.confidence` and every `same_as_candidate` edge carries a
resolution `score`. Those numbers are **similarity/provenance heuristics, not probabilities**:
a Jaro-Winkler/Levenshtein composite of `0.94` does not mean "94% likely to be the same entity".

Phase 13 adds `aletheia.core.calibration`, which fits a monotone map from a raw score to a
calibrated probability of a true match from labelled matched/unmatched pairs:

- **Platt scaling** (`method="platt"`) — a logistic fit `sigmoid(slope * score + intercept)` with
  Platt's target smoothing, trained by Newton-Raphson.
- **Isotonic regression** (`method="isotonic"`) — a non-parametric monotone step fit via
  pool-adjacent-violators.

The resolver reports this per candidate, and therefore per `same_as_candidate` edge, under
`resolution.calibrated` / `resolution.calibrated_probability`:

- `calibrated: false`, `calibrated_probability: null` — no calibrator was supplied, or the
  calibrator is **untrained** (fewer than `MIN_LABELED_PAIRS` pairs, or missing one class). The raw
  `score` is still present and is still a similarity heuristic.
- `calibrated: true` — a trained calibrator produced `calibrated_probability` in `[0, 1]`. The raw
  `score` is preserved next to it.

A consumer must never treat `confidence`/`score` as a probability unless `calibrated` is `true` for
that edge. The current fit is trained on a **synthetic** fixture (`tests/fixtures/calibration_pairs.json`,
deterministically generated); it demonstrates the mechanism, not a production-calibrated model. Real
calibration is deferred until labelled pairs from authorised investigations exist — the component and
its `calibrated` flag are the stable contract.

