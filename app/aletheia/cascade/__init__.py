"""Phase 17 pivot cascade.

- :mod:`aletheia.cascade.routing` — descriptor-derived routing graph and the
  build-time coverage invariants (P17.2).
- :mod:`aletheia.cascade.seeds` — seed autodetection, canonicalization, dedup
  (P17.2).
- :mod:`aletheia.cascade.claims` — claim normalization, dedup, and strong-key
  blocking (P17.3).
- :mod:`aletheia.cascade.extractors` — claim -> seed pivot extraction with the
  section-7 gates (P17.3).
- :mod:`aletheia.cascade.matching` — pure string/phonetic/graph/temporal
  matchers (P17.4).
- :mod:`aletheia.cascade.phash` — stdlib perceptual image hashing (P17.4).
- :mod:`aletheia.cascade.priors` — provisional base-rate priors (P17.4).
- :mod:`aletheia.cascade.scoring` — likelihood-ratio scoring, tiers, and the
  calibration hook (P17.4).
- :mod:`aletheia.cascade.evidence` — the claim-pair evidence decision table
  (P17.4).

Nothing in this package changes existing CLI / router / adapter behavior; the
cascade steps that consume it land in later P17 items.
"""
