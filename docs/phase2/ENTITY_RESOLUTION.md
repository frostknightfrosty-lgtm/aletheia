# Phase 2 - Entity Resolution Policy

Aletheia uses a conservative, explainable two-stage policy.

1. Values are normalized by entity type. Exact canonical equality is an automatic deduplication signal.
2. Fuzzy similarity uses Jaro-Winkler and normalized Levenshtein distance through RapidFuzz. These scores create `SAME_AS_CANDIDATE` edges only; they are not treated as source evidence and do not automatically merge entities.

The composite score is `0.65 * Jaro-Winkler + 0.35 * normalized Levenshtein`. The default candidate threshold is 0.88. The configured 0.985 auto-merge threshold is intentionally non-authorizing: policy requires exact canonical equality for merges.

This design prevents a typo-tolerant matcher from silently converting two potentially distinct real-world identities into one.
