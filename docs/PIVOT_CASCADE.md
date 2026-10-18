# Pivot Cascade — Design (Phase 17)

> Status: design draft **v2 — maximal scope, for review; not implemented**. No
> cascade code exists yet. This is the review artifact that precedes
> implementation, per the project sequence (design → tests → CI-verified code).
> Nothing here changes the current CLI, router, adapter enforcement, or
> live-investigation behavior. Prerequisites: everything below is achievable
> with free / open-source tools or free-tier API registrations only —
> **nothing paid**, and no source is added without its own scoped review.

Revision note — v2 adds, on top of v1: seed autodetection, likelihood-ratio
scoring (Fellegi–Sunter) with base-rate priors, falsification-first review and
Analysis of Competing Hypotheses, union-find conflict propagation, source
reliability grading, VOI-based scheduling with adaptive budgets, case memory
with cross-run caching and re-audit diffs, a much wider free-source playbook
(archived web, open knowledge graphs, key servers, CT/RDAP, common crawl),
human-loop tooling (confirm fast-lane, next-actions checklist, redaction,
purge), a third-party firewall, a synthetic-world + adversarial test program,
and an explicit list of free-but-rejected techniques.

## 1. Objective

Given any seed (or seed set, or raw text containing seeds), the engine must:

1. Type and normalize the seed(s), then run every adapter that supports them.
2. Normalize findings into claims; cluster claims into subject identities with
   a calibrated, evidence-based score.
3. Extract **typed pivots** from attributable findings only.
4. Re-run adapters on those seeds — adapter -> adapter -> adapter — inside
   budgets and rate limits.
5. Repeat until saturation or a depth/budget/time cap, recording why.
6. Emit a tiered identity report, a cumulative case dossier, and a complete
   auditable chain from the first seed to every data point.

### Non-goals (unchanged policy)

- No paid-only sources; no breach corpora beyond free registered APIs; no
  login-walled scraping; no ToS violations; no Tier 5 activity. `GATES.md` and
  the tier model are unchanged.
- No fabricated unification: the cascade never merges identities without
  evidence; uncalibrated scores are always marked.
- No third-party expansion (see firewall, section 11).
- No change to structural rules: Docker-isolated adapters, egress proxy,
  hash-chained audit, `legal_only=true`, authorization assertions.

## 2. Principles

1. **Evidence-gated expansion** — only attributable findings spawn searches.
2. **Capability-driven routing** — routes derive from each adapter's
   `input_types` / `output_types` descriptors; no hardcoded lists.
3. **Falsification-first** — before any merge, the engine actively looks for
   the strongest evidence *against* it (competing hypotheses, vetoes).
4. **Deterministic and resumable** — stable ordering, seeded RNG recorded,
   frontier persisted in the checkpoint; `resume` continues mid-cascade.
5. **Honesty over coverage** — OBSERVED vs INFERRED vs PIVOTED stay separate;
   probabilities printed only when the calibrator is trained.
6. **Stopping is a feature** — saturation, diminishing returns, vetoes, and
   budgets end expansion early and record the reason.
7. **Nothing paid** — free tools, free datasets, free-tier registrations only.

## 3. Seed layer

- **Autodetection**: accept raw text; extract candidate seeds (usernames,
  emails, phones, URLs/domains, IPs, crypto addresses, VINs, company names)
  via validators/regex; present the typed list for confirmation before a live
  run. Multi-seed input runs as one investigation tree set (existing
  multi-seed machinery).
- **Canonicalization** per type (case, URL/IDN normalization, E.164 for
  phones) drives dedup: a seed never runs twice in a run.
- **Variant generation** for username-class seeds (separator/leet/suffix
  families, transliteration variants for non-Latin scripts), capped and
  low-priority; each variant hit is a candidate until clustered.

## 4. Routing graph (the "adapter to adapter" mechanism)

Runtime graph: `SeedType` nodes -> `adapter` edges (from descriptors) ->
`EntityType` nodes -> `pivot` edges (from extractors) -> `SeedType` nodes.
Expansion = walking that graph. A build-time test asserts **every `SeedType`
member has >= 1 route**; thin-coverage types are recorded in the report.

| Seed type | Adapter families (existing modules) | Typical pivots yielded |
| --- | --- | --- |
| username | sherlock, identity (maigret, instaloader), social_username, social_profile, search_engines, code_search | url, social_account, person attrs, image |
| person_name / name | search_engines, academic_search, government_records_us, corporate_records, corporate_registry, sanctions watchlists, patents_trademarks | url, records, company, social_account |
| email | phase 5c batch (Gravatar/keyserver-class), email_auth, leak_checkers (keys), code_search | social_account, image, email_auth_record, breach hints, domain |
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
  github.com/frost2233 --(code_search + GitHub free endpoints)--> [candidate email]
    email --(Gravatar, WKD/keyservers, email_auth, leak_checkers*)--> avatar, key bindings, DNS records
      domain --(theharvester, ssl_tls, crt.sh-class, RDAP-class)--> hosts, cert observations, more candidates
```
*keys-gated adapters skip without secrets, as today.

## 5. Claim layer, blocking, and conflict ledger

- `Claim = {type, value, source_adapter, source_url, observed_at, confidence,
  raw_evidence_sha256, seed_index, parent_finding_id, source_grade}`.
- **Blocking** for comparisons: candidate pairs are generated only within
  strong-key blocks (shared email, phone, domain, or exact handle) — avoids
  O(n^2) comparisons and coincidence-chained false links.
- **Conflict ledger**: when two claims contradict (e.g., two different rare
  names on two accounts), both are kept and flagged; nothing is silently
  overwritten.

## 6. Evidence engine (the core)

### 6.1 Matchers

- String: Jaro-Winkler, Levenshtein, token-set ratio, IDF token weighting,
  phonetic keys (Soundex/Metaphone-class, pure stdlib), nicknname/full-name
  expansion, transliteration variants.
- Image: exact `sha256` match, perceptual hashes (pHash/DCT + aHash/dHash
  ensemble), avatar reuse detection; optional OCR text -> claims.
- Graph: mutual declared links, shared outbound link sets, shared personal
  domain, mutual-follow overlap (public data only).
- Temporal: account-era coherence, activity-window overlap, recency decay
  (older claims weigh less for "current identity", still count for history).

### 6.2 Scoring — likelihood ratios, not ad-hoc weights

Each evidence class carries estimated `m = P(evidence | same person)` and
`u = P(evidence | different person)`; the score is the sum of log-likelihood
ratios (Fellegi–Sunter form). v1's weight table becomes the initial LR table
(reviewable constants), tuned by calibration once labels exist.

**Base-rate prior**: prior log-odds for a candidate match scale with handle
entropy and name rarity (a collision-prone handle like `frost` starts lower
than a high-entropy one), with per-platform adjustments. Marked uncalibrated
until the calibrator is trained; collisions are reported as "ties to >= N
distinct identities" when conflicts exist.

| Class | Evidence | Initial LR |
| --- | --- | --- |
| HARD | identical email / phone across accounts | very strong |
| HARD | mutual declared links | very strong |
| HARD | same PGP key / same committed email | very strong |
| STRONG | avatar perceptual-hash match | strong |
| STRONG | identical bio / media asset hash | strong |
| STRONG | same personal domain | strong |
| STRONG | explicit cross-platform declaration | strong |
| MEDIUM | IDF name match + era coherence | medium |
| MEDIUM | country + window + tag overlap | medium |
| MEDIUM | handle-variant family + era | medium-weak |
| WEAK | common-name similarity, broad geography | weak |
| VETO | conflicting rare identifier / rare name / demographics | exclude |

### 6.3 Tiers and hypothesis review

- **confirmed**: >= 1 HARD, or >= 2 independent STRONG, surviving falsification.
- **probable**: 1 STRONG + >= 1 MEDIUM, or >= 3 independent MEDIUM.
- **possible**: everything above WEAK.
- **excluded**: any surviving VETO.

**Falsification-first**: before confirming, a dedicated review pass runs
disconfirming probes (rare-attribute conflicts, era contradictions, name
conflicts) and records the strongest disconfirming evidence in the ledger.

**Analysis of Competing Hypotheses (ACH)**: each hit is evaluated against
hypotheses `H_subject` (belongs to the investigation subject), `H_other`
(different person), `H_shared` (shared/sockpuppet account). Evidence is scored
consistent / inconsistent / neutral per hypothesis; merges require `H_subject`
to survive with a margin over the best alternative, and the report shows the
surviving hypothesis and what would falsify it.

**Union-find with conflict propagation**: confirmed merges form an equality
graph (transitive); if a later veto contradicts a confirmed chain, the chain
is re-opened, the weakest link demoted, and the contradiction recorded — no
silent split, no silent merge.

**Source reliability grading**: every adapter/source carries an
Admiralty-style grade (reliability A–F, credibility 1–6); claims inherit the
grade; low-grade sources alone can never clear a tier gate.

## 7. Pivot extraction and gates

| Observed claim | Candidate seed | Gate |
| --- | --- | --- |
| profile link | url / domain | cluster confirmed or probable |
| declared real name | person_name | confirmed only |
| email in page/commit/PGP metadata | email | confirmed only |
| handle mention ("find me at @x") | username | confirmed or probable |
| avatar/media asset | image (local pHash only) | probable+ |
| declared location | filter / geolocation seed | confirmed, low priority |

Policy: personal identifiers (email, phone, person_name) pivot only from
**confirmed**; structural seeds from **confirmed or probable**; media seeds
from probable+ for local comparison only (no third-party biometrics);
possible/excluded spawn nothing.

## 8. Scheduler

- **Priority = value of information (VOI)** — expected uncertainty reduction
  per unit cost: `prior attribution probability x sum(adapter yield history x
  expected pivot rarity) / cost`, with depth penalty and freshness terms.
  Yield history comes from the existing benchmark store.
- **Adaptive budget**: default depth 3; +1 (cap 5) when HARD evidence is
  found and `pivot_scope` allows; de-escalate under time pressure. Per-type
  caps (emails <= 10, phones <= 5, names <= 5, domains <= 25, urls <= 50).
- **Politeness**: existing per-adapter egress envelope plus optional per-host
  sub-limits; request coalescing via the cache (section 9).
- **Stop reasons**: `saturated | diminishing_returns | depth | budget | time |
  user_stop`. Saturation = one full pass adds no claim above the floor;
  diminishing returns = marginal VOI below threshold.
- **Resume**: frontier in checkpoint; stable ordering; RNG seed recorded.
- **Decision ledger**: every pivot decision (claim, gate, score, priority,
  budget) is logged and replayable (`cascade review mode`).

## 9. Memory and the case model

- **Case file**: runs merge into one subject-centric identity graph with
  snapshots and a timeline (events: first seen, updated, retracted). Reports
  are per run + cumulative dossier.
- **Cross-run cache**: per-source TTL (profile existence ~30 days, DNS ~7,
  configuration), cache hits marked in the trail (no egress); `--no-cache`
  for fresh sweeps; deterministic replays use the cache only.
- **Re-audit / watch diffs**: `reaudit --case X` re-runs and diffs against
  the last snapshot: new appearances, changed bios, new exposures, resolved
  blind spots. Nothing is re-asked that is still fresh.
- **Label store**: confirmations persist under the data root (never
  committed); feeds `core/calibration.py` (Platt / isotonic).
- **Blind-spot registry**: per-source known limits (e.g., "no public email
  fields") so the engine never wastes budget on dead pivots and the report
  lists exactly what remains unreachable and why.

## 10. Free-source playbook (nothing paid)

Seed-type expansion candidates, all free tools / datasets / free-tier keys.
Each new source requires its own scoped review before integration.

| Area | Source (free) | Yields |
| --- | --- | --- |
| Archived web | Wayback Machine CDX + archive-class mirrors | deleted/changed profiles, old bios, former handles |
| Open knowledge | Wikidata (SPARQL), Wikipedia, ORCID, OpenAlex-class | name -> declared social handles, affiliations |
| Crypto-identity | key servers (keys.openpgp.org), WKD, GitHub `.keys` | email<->key bindings, SSH fingerprints reused elsewhere |
| Avatar check | Gravatar (md5-based) | avatar presence + pHash cross-match |
| Code hosts | GitHub public endpoints (events, keys, commits, gists) | emails (incl. noreply patterns), orgs, timelines |
| Domain intel | crt.sh-class CT logs, RDAP, DNS (email_auth) | subdomains, cert observations, infrastructure |
| Web corpora | Common Crawl index | pages mentioning handle/domain |
| Game/community | Mojang/NameMC-class name history | handle renames, UUID history |
| Username sets | WhatsMyName dataset, Blackbird-class FOSS enumerators | wider username coverage (own review per tool) |
| Exposure | XposedOrNot (free), LeakIX community key, GrayhatWarfare free tier, psbdmp-class paste index | breach/exposure hints (paste index is Tier 4 policy scope; own review) |
| Search | search_engines batch + per-seed-type query packs (site:, intext: templates) | fresh web mentions |
| Social graph | public follow/friend lists | mutual-overlap evidence (medium) |
| Geo | Mapillary/Nominatim/OSM, exiftool, steg analysis (existing) | place evidence from images |

Media handling: reverse-image-search scraping is excluded (ToS); the engine
uses local perceptual hashing, EXIF, OCR, and archived avatar captures only.

**Free-tier key registrations (Gate 3 class)**: reddit-api, youtube-api,
LeakIX community, GrayhatWarfare free tier, GitHub token (higher rate
limits). Each unlock is listed in the report's next-actions checklist.

**Excluded even though free** (policy): holehe-class reset-endpoint probing
(ToS/gray), reverse-image-search scraping (ToS), people-search/dossier
scraping (ToS/law), darkweb indexes (Gate 6), stealer-log corpora beyond
existing leak-checker scope, brute-force enumeration of non-public endpoints.

## 11. Firewalls and honesty

- **Third-party firewall**: only identifiers attributable to the
  investigation subject(s) may spawn pivots. Identifiers of other people
  (followers, friends, family, colleagues) are observed-only, never pivoted,
  unless separately authorized.
- **Minor / health pause**: jurisdiction-warning signals (existing `warnings`
  module) pause personal-identifier pivots and surface the signal to the
  operator.
- **Modes**: `owner_self_audit` (authorization assertion + pivot_scope;
  personal pivots permitted per scope) vs `subject_investigation` (default;
  personal pivots off unless declared per type). Both recorded in the
  manifest and audit chain.
- **Retraction**: `--not-mine` marks `same_as_excluded`, retracts the subtree
  from further pivoting, keeps claims for audit, marked.
- **Collision honesty**: report ties to multiple distinct identities when
  conflicts exist; never print uncalibrated numbers as probabilities.
- **Redaction & retention**: reports can be generated `--redact`ed for
  sharing; labels and cache live under the data root (never committed); a
  `purge` command deletes case artifacts on request.

## 12. Reporting and the human loop

- Artifacts: `cascade_trail.json` (every hop, parent-linked),
  `dossier.json` (tiered identity, evidence chain per field),
  `coverage.json` (coverage audit), plus upgraded `report.json` /
  `report.pdf` / `report.stix2.json` / `graph.graphml`.
- **Coverage audit**: end-of-run assertion that every matching adapter ran or
  has a skip reason, every pivot type had a gate evaluation, and egress
  accounting balances — the "did we really squeeze it" proof.
- **Next-actions checklist**: free keys to register (and exactly what each
  unlocks), clusters to confirm, missing seed types to supply, sources
  blocked that may open later.
- **Confirm fast-lane**: mine / not-mine / unsure per cluster (bulk-friendly);
  unsure stays a candidate; confirmations become calibration labels.
- **Explainability**: score decomposition per claim (log-odds ledger), and
  `cascade review mode` to replay every decision.

## 13. Testing and verification program

- **Synthetic identity worlds**: fixture corpora with N synthetic people who
  share handle fragments and near-names, with ground truth; CI asserts tier
  assignments and micro/macro precision — the engine must separate people
  correctly before it is ever pointed at a live subject.
- **Adversarial collision traps**: fixtures where another synthetic person
  deliberately matches a handle on 3 platforms with conflicting rare
  identifiers; the engine must exclude, not merge.
- **Property tests**: no merge without the evidence rule; vetoes always win;
  determinism (same seeds + budget => identical order and trail); dedup
  invariant; budgets never exceeded; egress only via proxy; third-party
  firewall holds.
- **Golden cascade run**: fixed fixture => stable trail hash (regression
  detector for scoring changes).
- **Failure injection**: proxy 429/503, bot walls, malformed HTML; assert
  blocked-recorded / no retry storms / partial results preserved.
- Parser preflight stays 49/49; all adapters keep executing in CI.

## 14. Data-model additions

- `Provenance`: + `parent_finding_id`, `cascade_depth`, `pivot_reason`
  (defaults keep single-pass output unchanged).
- `RelationshipType`: + `same_as_confirmed`, `same_as_excluded`,
  `pivoted_from` (retain `same_as_candidate`).
- New: `PivotCandidate`, `ClusterDecision`, `IdentityTier`, `SourceGrade`,
  `Hypothesis`; manifest gains `frontier`, `budget`, `stop_reason`,
  `case_id`, `mode`.
- All additions additive/backward compatible; report schema gains optional
  blocks only.

## 15. Build plan (each step CI-verified; docs commits separate from code)

1. **P17.1** — this design document (v2) + PROJECT_DIRECTION pointer.
2. **P17.2** — cascade models + descriptor-derived routing graph + coverage
   invariant test + seed autodetection.
3. **P17.3** — claim normalization + blocking + pivot extractors + fixtures.
4. **P17.4** — matchers, perceptual hashing, LR scoring, base-rate priors,
   calibration hook.
5. **P17.5** — falsification pass + ACH + union-find conflict propagation.
6. **P17.6** — VOI scheduler + adaptive budgets + stop policy + resume +
   decision ledger.
7. **P17.7** — case memory + cache/TTL + re-audit diffs.
8. **P17.8** — CLI + trail/dossier/coverage outputs + next-actions checklist
   + redaction/purge; parser preflight stays 49/49.
9. **P17.9** — synthetic worlds + adversarial + failure-injection suites in
   CI.
10. **P17.10** — fixture dry-run -> local suite -> CI -> live cascade on the
    owner's own seed with owner confirmations; first real calibration labels.

## 16. Honest ceilings

- Private data no public/free source exposes is unreachable by chaining; the
  cascade maximizes the public trail and nothing more.
- Exposure data stays within free registered APIs; paid corpora remain out of
  scope by policy, not by inability.
- Platform walls (login walls, bot protection, 429s) cap specific sources;
  they are recorded as blocked, never worked around.
- Collisions: for a shared handle some hits stay permanently "possible
  others"; that is the system being correct, not weak.
- Location stays mostly declared or weakly inferred, explicitly marked.

## 17. Open questions for review

1. Adaptive depth: default 3, escalate to 5 on HARD evidence in
   `owner_self_audit` mode — confirm.
2. `pivot_scope` defaults per mode (owner mode: email/name on, phone on?).
3. Case model: opt-in `--case X` (proposed) or always case-attached?
4. Cache TTL defaults (30d profiles / 7d DNS proposed) — confirm.
5. Whether psbdmp-class paste indexing proceeds once its own Tier 4 scoped
   review is written (independent of the cascade).
