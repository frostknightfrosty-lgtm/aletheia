# Pivot Cascade — Design (Phase 17)

> Status: design draft **v3 — maximal scope, for review; not implemented**. No
> cascade code exists yet. This is the review artifact that precedes
> implementation, per the project sequence (design → tests → CI-verified code).
> Nothing here changes the current CLI, router, adapter enforcement, or
> live-investigation behavior. Everything below runs on free / open-source
> tools or free-tier API registrations only — **nothing paid**. Tier 2–4
> sources are enabled by project policy and marked review-gated; the Tier 5
> floor is unchanged; no source is added without its own scoped review.

Revision note — v3 adds, on top of v2: (a) the **universal seed horizon** —
any entry point, including raw pasted text or a screenshot, a location, a
name, an organization, an image, a document, a phone, a crypto address, a
vehicle or a patent, is a first-class start with its own playbook and
bridge-claim class-jumping; (b) a **classified expansion policy** — every
item previously listed as "excluded though free" is now sorted against the
Florida Tier ladder: Tier 2–4 items are included as review-gated expansions
(email-existence checks, GHunt on the operator's own account, people-search
free tiers, face search free paths, stealer-log checkers, paste indexes,
reverse-image search, dark-web indexes at Gate 6), while the Tier 5 floor
(unauthorized access, interception, criminal-marketplace transactions,
stalking/harassment) and paid-only defaults stay out; (c) a Wave-2 build
phase for those expansions. v2 brought: seed autodetection, likelihood-ratio
scoring (Fellegi–Sunter) with base-rate priors, falsification-first review
and ACH, union-find conflict propagation, source grading, VOI scheduling
with adaptive budgets, case memory with caching and re-audit diffs, the wide
free-source playbook, human-loop tooling, the third-party firewall, and the
synthetic-world test program.

Directive addendum — **2026-10-18**: the owner directed that **everything
accepted in the 111-candidate verification sweep and everything permitted by
the Florida project policy but not yet integrated be fully integrated, wired,
and working**, superseding the earlier narrower Wave-2 wording. Section 15
carries this as P17.11–P17.12; the item-by-item status inventory lives in
[`SOURCE_COMPLETENESS.md`](SOURCE_COMPLETENESS.md). All standing constraints
are unchanged: nothing paid, the Tier 5 floor, a scoped review per source
before code, and no fabricated evidence.

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

- No paid-only sources or paid default dependencies (Gate 3); no Tier 5
  activity — unauthorized computer access, communications interception,
  criminal-marketplace transactions, stalking/harassment. Tiers 1–4 are
  enabled by project policy; ToS-hostile-public sources are Tier 2 and
  enabled, with per-source risk recorded at integration.
- No target-account logins: adapters read public surfaces; the single
  authenticated-workflow exception is the operator's own account with
  explicit authorization (the GHunt pattern).
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
8. **Universal horizon** — any entry point is first-class: a playbook for
   every `SeedType`, raw-text/screenshot autodetection, and bridge claims
   that jump between classes until that class is honestly exhausted.

## 3. Seed layer

- **Autodetection**: accept raw text — or an image/screenshot via OCR — and
  extract candidate seeds (usernames, emails, phones, URLs/domains, IPs,
  crypto addresses, VINs, company names, names, places, document metadata)
  via validators/regex; present the typed list for confirmation before a
  live run. Multi-seed input runs as one investigation tree set (existing
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

### 4.1 Universal seed horizon — every entry point is first-class

"Anything the operator inputs" is a design invariant, not a slogan. Raw text
or a screenshot is autodetected into typed seeds (section 3); every
`SeedType` member has a playbook below; and every hop re-runs **bridge
extraction** — the mechanism that makes the cascade jump between classes.

**Bridge claims (the class-jumping mechanism).** A bridge claim is any claim
that is itself a seed for another class: `url <-> domain`, `email <-> domain
<-> avatar`, `image <-> place <-> device`, `name <-> records <-> org <->
officers`, `phone <-> person`, `crypto_address <-> donation pages <->
handles`, `file <-> metadata <-> author`, `ip <-> host <-> domain <-> site`,
`company <-> officers`, `intellectual_property <-> inventors`, `vin <->
registries`. Bridge extraction runs on *every* claim at *every* hop; it is
not hardcoded per seed type. A build-time test asserts every `EntityType`
resolves to >= 1 bridge extractor or an explicit terminal classification.

**Per-seed playbooks** (first wave -> convergence -> squeeze):

| Seed | First wave | Convergence path | "Squeezed" means |
| --- | --- | --- | --- |
| username | sherlock, identity, social_username/profile, search, code, WhatsMyName-class | avatars/bios/cross-links -> clusters; profile links -> domains/emails | all adapters ran; variants tried; profile links evaluated; no new claims |
| email | Gravatar, WKD/keyservers, email_auth, exposure checks, code search, review-gated existence checks | avatar -> pHash vs accounts; key -> identity; domain -> infra | every free email-intel source ran; avatar compared; domain exhausted |
| phone | PhoneInfoga-class, libphonenumber | corroboration attribute; messaging handles where public | carrier/geo + free lookups exhausted; recorded as thin if so |
| person_name / name | search, academic, records, registry, sanctions, patents, open knowledge graphs | auto-bundled with context (place/age/org) -> candidate accounts | record families exhausted; disambiguation shown against context |
| geolocation | geo/image adapters; records tied to place | context filter + intersection boost; place -> orgs/persons via records | imagery/records exhausted; honest "place intelligence" if no person is bound |
| domain / url | theHarvester, ssl_tls, infra, ip_intel, email_auth, CT, RDAP, crawl/archive | emails/people on site; infra -> more domains | DNS/auth/CT/RDAP/crawl/archive pulled; extracted emails pivoted |
| ip | ip_intel, infra, ssl_tls | reverse resolution -> domains -> sites -> people | reverse resolutions exhausted; hosting class recorded |
| image / file_path | exiftool, geo-image, steg, OCR; local pHash | GPS -> place; device/time; author metadata -> name; reuse -> accounts | metadata/steg/OCR/hash cross-match done |
| crypto_address | crypto_blockchain | transactions -> counterparties; donation pages -> handles | graph classified; public linkage recorded |
| company_name / bank_name | registry, records, sanctions, patents | officers/directors -> person cascade | registries exhausted for relevant jurisdictions |
| intellectual_property | patents/trademarks | inventors/assignees -> person/org cascade | jurisdiction sets exhausted |
| lobbyist_name | government records | filings -> employers/clients -> people | disclosure sets exhausted |
| vin | transport registry adapters | vehicle facts; owner data only where public | reachable facts recorded; ownership ceiling stated |

Honest convergence notes: an isolated place, phone, or VIN has no person in
it — the engine returns *place/vehicle intelligence* plus any people bound to
it by public records, and says so. Name seeds are auto-bundled with supplied
context (`ContextFilters`) to fight ambiguity. Multiple pasted seeds run as
one investigation with the intersection engine.

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
| STRONG* | face-search match (review-gated; free paths only; never sole basis) | strong, capped |
| MEDIUM | IDF name match + era coherence | medium |
| MEDIUM | country + window + tag overlap | medium |
| MEDIUM | handle-variant family + era | medium-weak |
| MEDIUM* | account-exists observation (endpoint existence checks; review-gated) | medium |
| MEDIUM* | exposure/stealer-check signal (review-gated; signal fields only) | medium |
| WEAK | common-name similarity, broad geography | weak |
| VETO | conflicting rare identifier / rare name / demographics | exclude |

`*` = review-gated expansions per section 10.1; these corroborate but can
never clear a tier gate alone.

### 6.3 Tiers and hypothesis review

- **confirmed**: >= 1 HARD, or >= 2 independent STRONG, surviving falsification.
- **probable**: 1 STRONG + >= 1 MEDIUM, or >= 3 independent MEDIUM.
- **possible**: everything above WEAK.
- **excluded**: any surviving VETO.

- **Falsification-first**: before confirming, a dedicated review pass runs
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
from probable+ — local comparison by default, face-search corroboration
only as a review-gated expansion (section 10.1) and never a sole basis;
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

Media handling: local perceptual hashing, EXIF, OCR, and archived avatar
captures run by default. Face search and reverse-image search are
review-gated expansions (10.1), free paths only.

**Free-tier key registrations (Gate 3 class — free keys only; no paid
defaults)**: reddit-api, youtube-api, LeakCheck free OSINT-Hub path, LeakIX
community, GrayhatWarfare free tier, Hudson Rock free endpoints, Shodan
free-account key, GitHub token (higher rate limits). HIBP direct email
lookups require a subscription and stay out under the nothing-paid rule
(XposedOrNot and the LeakCheck free path cover that class). Each unlock is
listed in the report's next-actions checklist.

### 10.1 Review-gated expansions — included (Tiers 2–4, project-allowed)

Each item below is allowed by project policy (`DIRECTIVE_AMENDMENT_FLORIDA.md`)
and is part of the Wave-2 build plan (P17.11); each still needs its own
source, license, scope, and implementation review before code. Permitted
sources with open interface facts (Blackbird licensing, Lullar's missing
machine interface) are resolved at that review under the 2026-10-18
completeness directive (`SOURCE_COMPLETENESS.md`): built once the review clears
the facts, or recorded with evidence if the facts block implementation.

| Expansion | Class | Conditions and safeguards |
| --- | --- | --- |
| Email-existence endpoint checks (holehe-class tools) | 2, public automation | owner-subject first (third-party firewall); per-site scoped allowlist; recorded as "account-exists observation"; no credential use; politeness limits |
| GHunt (Google-account surface) | 3-class, operator-owned account | only on the operator's own Google account with explicit authorization; read-only output |
| People-search aggregators (TruePeopleSearch, Whitepages free, PeekYou) | 4, aggregators | free paths only (paid-only products rejected); politeness; firewall; coverage limits recorded |
| Face search (free-path services; e.g. Search4Faces) | policy-allowed | free paths only (paid subscriptions such as PimEyes excluded by nothing-paid); corroboration only, never a sole basis |
| Stealer-log checkers (Hudson Rock, LeakRadar) | 4, stealer logs | structural safeguard before any credential-field parsing; signal/existence fields preferred; found credentials are never used for any login |
| Paste indexes (psbdmp-class, LeakCheck OSINT-Hub) | 4, leak indexes | flag-only storage — existence, date, source name; never dump contents beyond evidence hashes |
| Reverse-image-search automation | 2, ToS-hostile public | per-engine terms analysis at review; free engines only; fallback stays local pHash + archived captures |
| Dark-web search indexes (Ahmia, Torch, OnionLand, DarkSearch) | 4, dark-web indexes | policy-allowed; **Gate 6 deferred** (no verifiable request contract; Tor setup) — adapter slot designed, activates when Gate 6 clears |
| Bulk/paste data processing | 4 | allowed by policy; subject scope and retention rules apply |

### 10.2 Stays excluded — Tier 5 floor and paid defaults

- Brute-force or any access to non-public / access-controlled endpoints
  (unauthorized computer access).
- CAPTCHA / paywall bypass.
- Using another person's credentials; authenticating against target services.
- Communications interception.
- Criminal-marketplace transactions (index lookup only — never buying dumps).
- Stalking / harassment patterns (e.g., reset-email spam at scale).
- Paid-only products and paid default dependencies (e.g., HIBP direct email
  lookups; OpenCorporates non-open access paths).
- ONYPHE (Free View limited to the operator's own systems).

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
- **Found-material rule**: credentials or dump contents encountered by any
  allowed source are never used, never stored beyond evidence hashes/flags,
  and never trigger authenticated activity.
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
  firewall holds; Tier 5 line holds (no credential-use paths); bridge
  coverage (every `EntityType` has an extractor or terminal classification).
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

Implementation status is tracked in `docs/CAMPAIGN_LOG.md` (the campaign's
working memory): P17.2 landed first (commit `7900ce4`), everything else below
is pending.

1. **P17.1** — this design document (v3) + PROJECT_DIRECTION pointer.
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
11. **P17.11** — source completeness (owner directive, 2026-10-18; supersedes
    the earlier Wave-2 scope): everything accepted in the 111-candidate
    verification sweep and every policy-permitted but not-yet-integrated
    source becomes fully integrated, wired, and working — darkweb_search
    behind container-level Tor (OnionSearch, TorBot, Piano, Intelligence X);
    transport_movement (OpenSky, BarentsWatch, Network Rail, National Rail,
    Deutsche Bahn); the not-yet-built accepted candidates (VENOM;
    PicImageSearch, tracelines, ShadowFinder, pybdshadow, youtube-geofind,
    GeoLocator, Betaface); re-review-and-rebuild of documented drops that
    have a free path (crypttrace CLI wrap, Unpaywall DOI endpoint, GitLab
    with a free token, a self-hosted SearXNG instance, CipherScan pinned by
    commit, Bron Vault offline, ERATV SPARQL, BreachDirectory and Leak-Lookup
    key paths; PatentsView, Google Patents, EUIPO, PublicWWW and Google
    Custom Search re-checked with evidence); the disabled sub-sources (OWASP
    SocialOSINTLM, scrawler, Zehef, tiktok-hashtag-analysis); and the
    policy-permitted set (LeakCheck, LeakRadar, OsintCat, OathNet, Blackbird,
    Lullar, Hudson Rock, GHunt, people-search free tiers, face-search free
    paths, paste indexes, reverse-image search). Email-existence checks
    (holehe-class) are already integrated (holehe, h8mail) — verify only, do
    not duplicate. Each source keeps its own scoped review before code;
    free-key registrations and provider permissions are user actions
    (Gate 3); externally blocked items are recorded with evidence and
    re-checked, never fabricated. Item-by-item status:
    `docs/SOURCE_COMPLETENESS.md`.
12. **P17.12** — completeness verification: exercise every newly integrated
    source in authorized runs where gates permit; copy per-source evidence
    from the artifacts (Gate 5); update verification statuses and the
    completeness tracker only from those lines.
13. **P17.13** — horizon completion (added by the campaign, 2026-10-18):
    Wayback CDX, Wikidata/ORCID, keyservers (WKD / GitHub `.keys`), GitHub
    endpoint expansion, Mojang/NameMC, WhatsMyName, social-graph lists, and the
    Phase 9 residuals (news_search, Open-Meteo, historical). Interleaves with
    Track 2 whenever no completeness item is locally unblocked; every source
    still gets its own scoped review first, and the registry, Dockerfile,
    parser, fixture, capture-case, and manifest counts grow exactly with it.

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
5. Wave-2 prioritization: which review-gated expansion first (proposed:
   email-existence checks + GHunt, then people-search free tiers, then
   exposure checkers, then face search; dark-web last, at Gate 6)?
6. Face search: corroboration-only (proposed) or allowed as STRONG alone
   with a margin over alternatives?

### Resolution — adopted provisionally by the campaign (2026-10-18)

The owner's autonomous-campaign mandate was executed on these provisional
defaults while the owner is away; any of them can be redlined later (they are
also listed as redline candidates in `docs/USER_ACTIONS.md`):

1. Adaptive depth: **adopted** — default 3, escalate to 5 on HARD evidence in
   `owner_self_audit` mode.
2. `pivot_scope`: **adopted** — owner mode (self-audit): email/name/phone
   pivots on; subject mode: personal pivots off unless declared in the
   lawful-basis.
3. Case model: **adopted** — opt-in `--case X`; no case attached by default.
4. Cache TTL: **adopted** — 30 days for profile-ish data, 7 days for DNS.
5. Wave-2 prioritization: **superseded** by the completeness wave order in
   `docs/CAMPAIGN_LOG.md` (keyless-first, waves A → B → C → D → E); dark web
   stays last, behind container-level Tor, live runs gated.
6. Face search: **adopted** — corroboration-only; never the sole basis and
   never a STRONG-alone path.
7. Source grades (raised by P17.5): the low-grade cap mechanism (an explicitly
   graded E/F source never clears a tier gate alone) lands with P17.5's
   scoring upgrade, but wiring `Claim.source_grade` into evidence items is
   deferred until a grading pass assigns real per-source grades. The
   F6-unrated default reads as "not yet graded", not "judged unreliable".
   Redline candidate: cap on F6-unrated too (which would hold every ungraded
   merge at or below "possible" until grading lands).
