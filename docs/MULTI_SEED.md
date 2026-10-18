# Multi-seed investigations

A run can carry more than one seed. Repeat `--seed` on the CLI, pass `seeds` to
`POST /v1/investigations`, or pass `seeds` to the MCP `investigate` tool. A
single seed keeps the original single-seed behavior (see "Compatibility").

```bash
aletheia investigate --seed domain:example.com --seed email:alice@example.com
```

## What happens

- **Per-seed scheduling.** Every adapter that supports at least one of the seeds
  is scheduled once per seed it supports. The manifest records the schedule as
  `pending_seeds` (`{adapter: [seed indexes]}`); the adapter only runs for the
  seeds its descriptor accepts.
- **Per-seed workspaces.** Each invocation writes its own workspace directory
  and `result.json`: `<adapter>@seedN` (N is 1-based) for multi-seed runs. The
  manifest's `tools_invoked` uses the same labels.
- **Independent trees, tagged provenance.** Before ingestion, every finding from
  a multi-seed invocation is tagged with `Provenance.seed_index` (0-based
  position in `manifest["seeds"]`), so each seed's expansion remains an
  identifiable evidence tree inside the single graph. Single-seed runs leave the
  field unset, so their artifacts keep the pre-multi-seed shape.

## Intersection pass

Entity resolution is unchanged except for two additions:

1. **Cross-tree corroboration boost.** An entity whose evidence comes from two
   or more seed trees gets a bounded boost on the candidates it participates in:
   `score * (1 + 0.05 * (trees - 1))`, capped at 1.0. The boost never creates a
   candidate (the raw threshold is applied first) and never feeds the Phase 13
   calibrator, which was trained on raw similarity scores. Every boosted
   candidate says so in its machine-readable explanation:
   `cross_seed_trees=0,1`, `cross_seed_boost=<raw>-><boosted>`, and
   `boost is a documented heuristic prior (5% per additional tree), not
   calibrator output`.
2. **Report statistics.** `report.json` gains `statistics.seed_count` and
   `statistics.cross_seed_entity_count` (entities seen under two or more trees),
   plus `seeds` and `context_filters` at the top level.

## Context filters

Optional filters: `--filter-country`, `--filter-age-min`, `--filter-age-max`,
`--filter-language`, `--filter-timezone` (CLI), `context_filters` (API/MCP). They
are stored in the manifest as `context_filters` and carried on every
`AdapterRunRequest`, so an adapter may use them as query hints; enforcement is
implemented where an attribute can actually be compared:

- Resolution flags any fuzzy candidate where **either** entity positively
  mismatches an active filter: the candidate keeps its score but its decision
  becomes `filtered_out` with a `context_filter_mismatch=...` explanation. It is
  still recorded (nothing is silently dropped), but it is no longer presented as
  an actionable candidate.
- **Only positive mismatches count.** An entity that records nothing for a
  filtered attribute is never excluded on that basis; absence of evidence is not
  a mismatch. Exact canonical merges are not filter-scoped: merging identical
  values is an equality fact, not an attribution judgment.
- Matching rules: `country` and `language` are case-insensitive token matches
  ("US" matches "United States (US)", "en" matches "en-US"); a filter longer
  than three characters may also match as a substring. No ISO-3166 dataset is
  bundled, so "US" does not expand to "United States". `timezone` matches by
  case-insensitive equality or substring against the recorded IANA string.
  Age filters apply only where an age is computable from `age`, `birth_year`, or
  an ISO `birthdate`/`birth_date`/`dob` (computed at the current UTC year).

## Compatibility

- Single-seed CLI/API/MCP calls behave as before; the only manifest addition for
  them is `pending_seeds: {adapter: [0]}` (plus empty `skipped`/`context_filters`
  keys).
- Legacy manifests that lack `pending_seeds` remain resumable: `resume` derives
  the remaining seed indexes from the `seeds` list.
- Existing run artifacts are untouched: workspace names, `tools_invoked` labels,
  and provenance for single-seed runs are unchanged.

## Honest limits

- The trees share one graph, one audit chain, and one storage run. "Independent
  tree" is a provenance tagging, not physically separate storage; a deliberately
  separated per-seed store remains future work if ever required.
- The 5%-per-tree boost is a documented heuristic prior, not a calibrated
  probability and not source evidence. It is visible in every explanation it
  touches, and the report notes that fuzzy candidates are never auto-merged.
- Filters narrow attribution; they do not redirect adapter queries, and no
  adapter currently consumes `context_filters` beyond receiving it on the
  request.
