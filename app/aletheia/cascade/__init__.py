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
- :mod:`aletheia.cascade.falsify` — falsification-first disconfirming probes
  (P17.5).
- :mod:`aletheia.cascade.ach` — Analysis of Competing Hypotheses (P17.5).
- :mod:`aletheia.cascade.merge_graph` — confirmed-merge equality graph with
  union-find conflict propagation (P17.5).
- :mod:`aletheia.cascade.ledger` — append-only hash-chained decision ledger
  (P17.6).
- :mod:`aletheia.cascade.scheduler` — VOI scheduler, adaptive budgets, stop
  policy, and resume checkpoints (P17.6).
- :mod:`aletheia.cascade.trail` — parent-linked cascade trail and its golden
  regression digest (P17.8).
- :mod:`aletheia.cascade.dossier` — tiered dossier artifact builder (P17.8).
- :mod:`aletheia.cascade.coverage` — coverage audit artifact and the end-of-run
  assertion (P17.8).
- :mod:`aletheia.cascade.next_actions` — next-actions checklist (P17.8).
- :mod:`aletheia.cascade.redact` — deterministic redaction for shareable
  artifacts (P17.8).
- :mod:`aletheia.cascade.engine` — deterministic cascade engine over an
  injectable observer; composes claims -> pivots -> scheduler -> evidence ->
  ACH -> merges and records the trail + ledger (P17.9).

Nothing in this package changes existing CLI / router / adapter behavior — the
``cascade`` CLI group is additive; the live (adapter-backed) observer wiring
lands in later P17 items.
"""
