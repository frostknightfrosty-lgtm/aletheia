"""Phase 17 pivot cascade (P17.2: seed layer + routing graph).

- :mod:`aletheia.cascade.routing` — descriptor-derived routing graph and the
  build-time coverage invariants.
- :mod:`aletheia.cascade.seeds` — seed autodetection, canonicalization, dedup.

Nothing in this package changes existing CLI / router / adapter behavior; the
cascade steps that consume it land in later P17 items.
"""
