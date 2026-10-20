# Completeness audit (P17.11–P17.12) — 2026-10-20

Scope: the owner's 111 accepted sources in
[`SOURCE_COMPLETENESS.md`](SOURCE_COMPLETENESS.md) and the registered Docker
adapters in `PROJECT_MANIFEST.json`. This is a documentation audit; every
number below is copied from a downloaded CI artifact, not typed from memory.

## Evidence baseline

- Source run: **39466252253** on commit `446ccab` (crypttrace #20).
  - `PARSER PREFLIGHT: PASS — 57/57 adapters have parser coverage`
  - `1132 passed, 1 warning`; `junit_total` 1132; `skipped_in_ci: []`
  - `DOCKER CAPTURE: PASS — 81/81 cases captured`
  - egress: `adapters=57 network_required=50 wired=50`
  - storage: 6/6 backends, `required_all: true`
  - `results.json`: 81 entries, 0 nonzero return codes
- Docs run: **39468982807** on commit `1df7750` (same tree, docs only).
- Local tier-1 suite at the verified tree: **1059 passed + 73 skipped = 1132**;
  the 73 skips are the Docker-dependent tests (no Docker on this host) and the
  five storage-service tests, all of which execute in CI.

## Manifest audit

- `tool_inventory`: 60 entries — 57 Docker adapters, `egress_proxy`, and two
  Python libraries (`rapidfuzz`, `reportlab`) recorded as `verified-source-read`.
- All 57 adapters are `verified-fixture`; there is no `unknown` or `pending`
  adapter in the tree.
- Every adapter has a fixture file named in its note and a synthetic
  provenance marker; the fixture files exist in `tests/fixtures/`.
- Wave A entries cite their own run and commit. Earlier batch entries cite
  their historical `CI run`/`Docker Verification run` in the same note field;
  the audit did not rewrite those citations, because a citation is only
  changed from a copied artifact.
- The crypto composite (`crypto_blockchain`) and the standalone `crypttrace`
  adapter are both present: the composite records crypttrace as a documented
  skip, and the separate adapter performs the Bitcoin-only trace. No duplicate
  network call is made by the composite.

## Tracker audit

- The tracker's own count is **83 of 111 wired** and **28 remaining**. This
  audit did not change the count; it verifies that every wired row's evidence
  is a run citation and that every remaining row carries a gate, owner action,
  or recorded blocker.
- Remaining work falls into three groups:
  - **Gate 6 (environment/registration):** dark-web engines (OnionSearch,
    TorBot, Piano, Intelligence X), rail/transport APIs (OpenSky, BarentsWatch,
    Network Rail, National Rail, Deutsche Bahn), and the §B dark-web engine
    notes.
  - **Gate 3 / owner account or key:** OWASP SocialOSINTLM, youtube-geofind,
    Betaface, PatentsView, Google Patents BigQuery, EUIPO, GitLab, and the §B
    free-registration sources (LeakCheck, LeakRadar, OsintCat, OathNet,
    Hudson Rock, GHunt).
  - **Recorded drops/blockers:** scrawler (interface), GeoLocator (upstream
    withdrawal), ERATV (no SPARQL/RDF), Google CSE (closed to new customers),
    PublicWWW (paid), and the §B license/coverage limits (Blackbird, Lullar,
    people-search, face-search, paste indexes, reverse-image automation).
- No remaining row is an unblocked, free, implementable source. The next
  build work is therefore owner-gated (Waves B–D) or the separate P17.13
  horizon expansion.

## Live coverage

- The only Gate 2 assertion on file remains `username:frost2233`; no live run
  was made for any image, shadow, point, crypto, or other source without an
  authorized target.
- Every Wave A source without an authorized target is `verified-fixture` with
  synthetic provenance; its container health, selftest, and parser/capture
  paths are exercised in CI. This is the honest ceiling, not a substitute for
  a live sweep.

## P17.13 horizon status

Recorded in `docs/PIVOT_CASCADE.md` §15 item 13, not part of the 111-source
count. Current status:

- **Already covered in substance:** Wayback CDX (the identity adapter's
  `wayback` module), and WhatsMyName-style username-site lists (the pinned
  maigret/sherlock paths already enumerate those sites; a separate list
  adapter would duplicate them).
- **Not yet built:** Wikidata/ORCID, keyservers (WKD / GitHub `.keys`), GitHub
  endpoint expansion, Mojang/NameMC, social-graph list ingestion, news_search,
  Open-Meteo, and the historical Phase 9 residuals. Each is a free/public
  source with no owner registration, but each needs its own scoped review,
  image, parser, fixture, capture case, manifest entry, and CI run before it
  can be counted.
- P17.13 is therefore **scheduled, not blocked**; it is the next free build
  queue after this audit. No adapter or count is claimed for it here.

## Conclusion

P17.11 (source completeness) and P17.12 (per-source evidence verification) are
complete for the 111-source directive: 83 wired, 28 remaining with a written
gate/owner/blocker reason, 57 registered adapters all `verified-fixture`, and
no live claim beyond the single authorized username. Waves B–D and the P17.13
horizon expansion remain; the former need owner registrations/keys, the latter
is the next free implementation queue.
