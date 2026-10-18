# Pivot Cascade — Design (Phase 17)

> Status: design draft for review — **not implemented**. No cascade code exists
> yet. This is the review artifact that precedes implementation, per the project
> sequence (design → tests → CI-verified code). Nothing here changes the current
> CLI, router, adapter enforcement, or live-investigation behavior.

This document specifies how Aletheia turns one seed into a full identity map by
chaining adapters under an evidence gate: **run → cluster → attribute → pivot →
repeat**, until saturation. It reuses the existing scheduling, resolver,
calibration, checkpoint, egress, and audit machinery.

## 1. Objective

Given any seed (or seed set) from the existing `SeedType` universe, the engine
must:

1. Run every adapter that supports the seed (today's behavior, `pending_seeds`).
2. Normalize findings into claims and cluster them into subject identities with
   an evidence-based score.
3. Extract **typed pivots** (new seeds: link, email, name, handle variant,
   domain, image, ...) from the findings the score attributes to the subject(s).
4. Re-run adapters on those seeds — adapter → adapter → adapter — inside
   budgets and rate limits.
5. Repeat until a full expansion pass adds nothing new (saturation), or a
   depth/budget/time cap trips, recording the reason (`stop_reason`).
6. Emit a tiered identity report plus a complete, auditable chain from the
   first seed to every data point.

### Non-goals (unchanged policy)

- No paid-only sources; no breach corpora beyond free registered APIs; no
  login-walled scraping; no ToS violations; no Tier 5 activity. `GATES.md`
  and the tier model are unchanged.
- No fabricated unification: the cascade never merges identities without
  evidence classes; uncalibrated scores are always marked.
- No change to structural rules: Docker-isolated adapters, egress proxy,
  hash-chained audit, `legal_only=true`, authorization assertions.

## 2. Principles

1. **Evidence-gated expansion** — the cascade advances only through findings it
   can attribute to the subject; everything else stays a candidate and spawns
   nothing.
2. **Capability-driven routing** — adapters already declare `input_types` and
   `output_types` (`AdapterDescriptor` in `core/models.py`). The routing graph
   is *derived* from those descriptors plus pivot extractors; there is no
   hardcoded adapter list to drift out of date.
3. **Deterministic and resumable** — stable priority ordering; `frontier` state
   persists in the run checkpoint; `resume` continues a cascade mid-flight.
4. **Honesty over coverage** — three output classes stay visually separate:
   OBSERVED (claims), INFERRED (links and tiers), PIVOTED (chains). A
   probability is printed only when the calibrator is trained.
5. **Stopping is a feature** — saturation, veto contradictions, and budgets end
   expansion early and record why.

## 3. The loop

```
        seeds
          |
          v
   run adapters (every adapter whose input_types match)
          |
          v
   claims  (findings normalized, deduped, canonicalized)
          |
          v
   evidence engine -> clusters + tiers
          |            (confirmed / probable / possible / excluded)
          v
   pivot extraction (gated by tier)
          |
          v
   frontier  (priority, dedup, depth, budgets, saturation check)
          |                                   |
          +------------- new seeds -----------+
          |
          v
   (saturation / budget / depth / time) -> report + dossier + trail
```

```
frontier = initial seeds
seen = {canonical(seed) for seed in frontier}

while frontier and not stopped:
    seed = frontier.pop_highest_priority()
    for adapter in routes_for(seed.type):            # derived from descriptors
        claims += normalize(run(adapter, seed))      # Docker + egress + audit
    clusters = evidence_engine.score(claims)         # tiers + vetoes
    for cluster in clusters.tiered(confirmed, probable):
        for pivot in extract_pivots(cluster):        # typed, provenance'd
            if pivot.type in pivot_scope and pivot.value not in seen:
                frontier.push(pivot); seen.add(canonical(pivot))
    stopped = check_stop(frontier, claims, budget)   # saturation/budget/depth/time
emit(report, dossier, trail, stop_reason)
```

## 4. Subsystems

### S1 — Seed typing, variants, canonicalization

- Inputs are already typed (`SeedType`). The cascade adds **variant
  generation** for username-class seeds (e.g. `frost2233` → `frost_2233`,
  `frost.2233`, `frost2233x`) as *candidate* pivots only; variants are
  low-priority (see S5) and every variant hit is a candidate until clustered.
- Canonicalization per type (lowercase, trim, IDN/URL normalization) drives
  dedup: a seed never runs twice in a run.

### S2 — Routing graph (the "adapter to adapter" mechanism)

The planner builds a typed graph at runtime:

- nodes: `SeedType` and `EntityType` members,
- edges: `adapter` (seed type → entity types it emits, from `input_types` /
  `output_types`), `pivot` (entity claim → seed type, from extractors in S3).

Expansion = walking that graph. Because every adapter already declares its
types, adding an adapter automatically adds its routes. A test (P17.2) asserts
**every `SeedType` member resolves to at least one route**; types with no
live-enabled adapter fall through to the generic web-search family and are
recorded as thin coverage.

Expected shape (authoritative wiring comes from the descriptors):

| Seed type | Adapter families (existing modules) | New seed types typically yielded |
| --- | --- | --- |
| username | sherlock, identity (maigret, instaloader), social_username, social_profile, search_engines, code_search | url, social_account, person attributes, image |
| person_name / name | search_engines, academic_search, government_records_us, corporate_records, corporate_registry, sanctions watchlists, patents_trademarks | url, records, company, social_account |
| email | phase 5c batch (Gravatar/keyserver-class lookups), email_auth, leak_checkers (keys-gated), code_search | social_account, image, email_auth_record, breach hints, domain |
| phone | phone-intel family (phase 5c scope) | carrier/geo hints, url |
| domain / url | theharvester, ssl_tls, infra, ip_intelligence, email_auth, search_engines, code_search | email, host, ip, tls_observation, web_search_result |
| ip | ip_intelligence, infra, ssl_tls | host, tls_observation, jurisdiction |
| image / file_path | exiftool, geolocation_image, social_geo_image | geo_evidence, place, ocr_text |
| crypto_address | crypto_blockchain | blockchain_intel_record, url |
| company_name / bank_name | corporate_registry, corporate_records, government_records_us, sanctions watchlists | legal_entity, filing, sanction, person |
| geolocation | social_geo_image, geolocation_image | geo_evidence, place |
| intellectual_property | patents_trademarks | intellectual_property_record |
| vin | transport_asset_registry | transport_asset_record |

Illustrative chain:

```
username:frost2233 --(sherlock, identity, social_username)--> accounts + urls
  github.com/frost2233 --(code_search)--> [candidate email seed]
    email --(email_auth, phase 5c batch, leak_checkers*)--> DNS/auth record, exposures
      domain --(theharvester, ssl_tls)--> hosts, certs, more candidate emails
```
*keys-gated adapters skip without secrets, as today.

### S3 — Claim normalization and pivot extraction

Every adapter output becomes a claim:

`Claim = {type, value, source_adapter, source_url, observed_at, confidence,
raw_evidence_sha256, seed_index, parent_finding_id}`

Pivot extractors turn claims into candidate seeds, e.g.:

| Observed claim | Candidate seed | Gate |
| --- | --- | --- |
| profile link (URL on a profile) | url / domain | cluster confirmed or probable |
| declared real name field | person_name | cluster confirmed only |
| email in page/commit/PGP metadata | email | cluster confirmed only |
| handle mention ("find me at @x") | username | cluster confirmed or probable |
| avatar/media asset | image (local pHash comparison only) | cluster probable+ |
| declared location | context filter / geolocation seed | confirmed only, low priority |

### S4 — Evidence engine (the "which findings are most likely" core)

Evidence classes with reviewable weights (constants, tuned with calibration):

| Class | Evidence | Weight |
| --- | --- | --- |
| HARD | identical email on two accounts | 0.95 |
| HARD | identical phone on two accounts | 0.95 |
| HARD | mutual declared link (A links B and B links A) | 0.90 |
| HARD | same PGP key / same committed email on a code host | 0.90 |
| STRONG | avatar perceptual-hash match (tunable Hamming threshold) | 0.80 |
| STRONG | identical bio / self-description string | 0.80 |
| STRONG | same personal domain featured by both | 0.80 |
| STRONG | explicit cross-platform handle declaration in a profile | 0.85 |
| STRONG | same media asset (sha256) reused as avatar/banner | 0.80 |
| MEDIUM | IDF-weighted name-token match + coherent era | 0.50 |
| MEDIUM | declared country + activity-window overlap + tag fingerprint | 0.40 |
| MEDIUM | handle-variant family with era coherence | 0.35 |
| WEAK | common-name similarity alone | 0.15 |
| WEAK | broad geography only | 0.10 |
| VETO | conflicting rare identifier (email/phone/PGP) | veto |
| VETO | conflicting rare real name (both populated) | veto |
| VETO | disjoint eras + conflicting declared demographics | veto |

Tier formation:

- **confirmed**: >= 1 HARD, or >= 2 independent STRONG;
- **probable**: 1 STRONG + >= 1 MEDIUM, or >= 3 independent MEDIUM;
- **possible**: above WEAK but below probable;
- **excluded**: any VETO outranks everything (retraction follows).

Pivot policy (defaults, reviewable): personal identifiers (email, phone,
person_name) pivot only from **confirmed**; structural seeds (url, domain,
username variants) from **confirmed or probable**; media seeds from probable+
and used only for local perceptual-hash comparison (no third-party biometric
services); possible/excluded clusters spawn nothing.

### S5 — Frontier scheduler

- **Priority** = rarity(type) x source confidence x adapter yield history
  - depth penalty - cost. Rarity proposal: email 1.0, phone 1.0, PGP 0.9,
  crypto 0.8, personal domain 0.7, handle variant 0.5, url 0.4, name 0.3,
  location 0.2.
- **Dedup**: canonical value per type; a seed never runs twice.
- **Retry**: at most one transient retry; 401/403/429 marks the source blocked
  for the run (recorded, never retried blindly).
- **Budget defaults (proposal)**: max depth 3; per-type caps (emails <= 10,
  phones <= 5, names <= 5, domains <= 25, urls <= 50); egress envelope per
  adapter as configured today; wall-clock cap per run.
- **Stop reasons**: `saturated | depth | budget | time | user_stop`.
  Saturation = one full expansion pass adds no new claims above the confidence
  floor.
- **Persistence**: the frontier lives in the run checkpoint; `resume` continues
  a cascade mid-flight exactly like today's pending-adapter resume.

### S6 — Guardrails

- Cascade mode requires the authorization assertion **and** an explicit
  `pivot_scope` declaration (which personal identifier types may be
  auto-pivoted). Both are recorded in the manifest and the audit chain.
- Retraction: `--not-mine` on a cluster marks it `same_as_excluded`, retracts
  its subtree from further pivoting, and keeps the claims for audit, marked.
- Gates unchanged: Tier 3 adapters without keys skip and are recorded; no
  Tier 5; `GATES.md` governs live runs.
- Every adapter run remains Docker-isolated, egress-proxied, and
  audit-chained.

### S7 — Reporting

- New artifacts: `cascade_trail.json` (every hop, parent-linked) and
  `dossier.json` (tiered identity fields, each with its evidence chain).
- Existing `report.json` / `report.pdf` / `report.stix2.json` /
  `graph.graphml` gain: identity tiers, evidence ledgers, and a cascade
  summary (seed paths expanded, depth reached, stop reason).
- OBSERVED vs INFERRED vs PIVOTED sections; uncalibrated scores labeled as
  such; collisions reported as "ties to >= N distinct identities" when vetoes
  or conflicts exist.

### S8 — Learning loop

- `confirm` command writes labelled pairs (cluster -> mine / not-mine) to a
  local labels file under the data root (never committed).
- `core/calibration.py` (Platt / isotonic, `MIN_LABELED_PAIRS`) fits once
  enough labels exist; reports switch from "score (uncalibrated)" to
  "probability (calibrated)" only when `trained` is true.
- Calibration changes reporting, not extraction; evidence weights stay
  reviewable constants.

## 5. Data-model additions (proposed)

- `Provenance`: + `parent_finding_id: UUID | None`, `cascade_depth: int = 0`,
  `pivot_reason: str | None` (defaults keep single-pass output unchanged).
- `RelationshipType`: + `same_as_confirmed`, `same_as_excluded`,
  `pivoted_from` (existing `same_as_candidate` retained).
- New models: `PivotCandidate`, `ClusterDecision`, `IdentityTier`;
  manifest gains `frontier`, `budget`, `stop_reason`.
- All additions are additive and backward compatible; the report schema gains
  optional blocks only.

## 6. Honest ceilings

- Private data that no public or free-registered source exposes is not
  reachable by any amount of chaining; the cascade maximizes the public trail,
  nothing more.
- Exposure data stays limited to free registered APIs (keys-gated); paid
  corpora and people-search databases remain out of scope by policy.
- Collisions are handled with tiers and vetoes, never assumed away; for a
  shared handle, some hits will be permanently "possible" others.
- Platform walls (login walls, bot protection, 429s) cap specific sources;
  these are recorded as source-blocked, not worked around.

## 7. Build plan (each step CI-verified; docs commits separate from code)

1. **P17.1** — this design document + PROJECT_DIRECTION pointer (docs only).
2. **P17.2** — cascade models + descriptor-derived routing graph + a test
   asserting every `SeedType` resolves to >= 1 route.
3. **P17.3** — pivot extractors per adapter family + fixture tests.
4. **P17.4** — evidence engine v1 (pure-stdlib pHash, IDF tokenizer,
   mutual-link detector, veto rules) + unit tests + calibration hookup.
5. **P17.5** — frontier scheduler + budgets, saturation, resume, audit-chain
   integration; deterministic fake-adapter tests.
6. **P17.6** — CLI surface + `cascade_trail.json` / `dossier.json` outputs;
   parser preflight stays 49/49.
7. **P17.7** — fixture dry-run -> local suite -> CI (Docker) -> live cascade
   on the owner's own seed with owner confirmations; weights tuned from the
   real outcome (first genuine calibration labels).

## 8. Open questions for review

1. `max_depth` default: 3 proposed; 4-5 for owner self-audits?
2. `pivot_scope` default: personal identifiers off unless declared, or on for
   owner-authorized runs?
3. Should **possible** clusters ever pivot (structural seeds only), or never?
   Proposed: never.
4. CLI shape: `aletheia cascade` as a new run type, or a new phase on the same
   manifest? Proposed: same manifest, new scheduled phase.
5. Calibration labels location: data root (proposed, never committed).
