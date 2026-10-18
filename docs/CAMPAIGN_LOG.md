# Aletheia Autonomous Campaign Log

> **Owner mandate (2026-10-18, evening).** Execute the entire remaining plan fully
> autonomously — Phase 17 pivot cascade (P17.2–P17.10), the source-completeness
> directive (P17.11–P17.12), horizon completion (P17.13), close-out — and stop only
> when nothing remains but owner-gated items (`docs/USER_ACTIONS.md`). Nothing paid;
> Tier 5 floor; evidence never typed (Gate 5); Tier 1–4 sources only.
>
> **This file is the campaign's working memory.** On every session start and after
> every context compaction, read `RESUME_STATE.json`, `HANDOFF.md`, then this file,
> in that order. Trust these anchors over memory; when in doubt, re-derive from
> `git log` and `gh run list`.

## NOW (edited in place — this is the current position)

- Campaign: **ACTIVE** — owner mandate received and executing.
- Position: **P17.6 pushed as `341f055`** (VOI scheduler + adaptive budgets +
  stop policy + resume checkpoints + hash-chained decision ledger; 22 new
  tests; local 879 passed + 65 environment-only skips → expected CI 944).
  Verification run starting. **P17.3 verified green**; **P17.4 verified
  green** (run `39155284979` on `db5f03e`, 896 passed); P17.5
  (`39156241115`) still watching.
- Next action: start **P17.7** (case memory + cache/TTL + re-audit diffs)
  locally while CI runs; copy evidence when the watches notify.
- In-flight CI: `39156241115` (P17.5 code `d561c9c` + docs `051625c`),
  `341f055`'s run starting.
- Last verified commit: `db5f03e` (run `39155284979`, docker-verification
  green; lines copied: parser 49/49; **896 passed**; capture 60/60; storage
  6/6).
- Owner-blocked (parked, never wait on): everything in `docs/USER_ACTIONS.md`.
- Decision defaults in force: see "Adopted defaults" below.

## Operating loop (per work item)

1. Pick the top unchecked queue item that is not parked.
2. Scoped review recorded first (license / terms / interface / permitted
   invocation / rate limit / tier / response-field screening), then implement
   (adapter, parser, fixture, capture case, manifest row).
3. Local suite green on this machine (`python -X utf8 -m pytest`, per repo docs).
4. Commit (code / docs / state separated) and push.
5. Start the CI watch in the **background**:
   `gh run watch <id> --exit-status --interval 30 *> "$env:TEMP\watch_<id>.log"`.
   Never poll.
6. While CI runs: begin step 1–3 of the next item locally (pipeline, don't idle).
7. On the CI notification: download the artifact
   (`gh run download <id> -D ci-artifacts-<id>`), copy evidence lines into the
   manifest / tracker / CHANGELOG, append a Log entry below, update `NOW`.
8. Milestone (≈ every 5 verified items, or any gate change): update
   `RESUME_STATE.json` + `HANDOFF.md` (state commit, LF-only, no BOM).
9. CI red: read the failing log tail, fix forward locally; max 2 attempts per
   failure class, then park with the copied failure excerpt and continue with the
   next unblocked item.

## Adopted defaults (provisional — owner may redline at any time)

- Adaptive depth: default 3; escalate to 5 on HARD evidence in `owner_self_audit`.
- `pivot_scope` defaults: owner mode — email/name/phone on; subject mode — personal
  pivots off unless declared in the lawful-basis.
- Case model: opt-in `--case X`.
- Cache TTL: 30 days for profiles, 7 days for DNS.
- Face search: corroboration-only, never the sole basis.
- Completeness wave order: keyless-first, waves A → E (see Queue).
- Dark web: built behind container-level Tor; live dark-web runs remain gated.
- Live runs: only for targets with a Gate 2 assertion already on file (today:
  `username:frost2233`). Any other target parks in `USER_ACTIONS.md`.

## Landmines (do not rediscover)

- PowerShell mangles em-dashes in console output; the artifact/state files are
  UTF-8. Trust the file, not the screen. If `Get-Content -Raw` misbehaves, fall
  back to `[IO.File]::ReadAllText($path)`.
- `|` inside quoted `gh --jq` arguments can split in PowerShell; prefer
  `--json` + `ConvertFrom-Json`, or single-quoted jq expressions.
- Windows Python: always `python -X utf8`.
- `RESUME_STATE.json` must stay LF-only, no BOM, valid JSON.
- Tests pin registry↔manifest consistency (e.g. `tests/test_ssl_tls_adapter.py`,
  `tests/test_email_auth_adapter.py`, `tests/test_phase3_manifest.py`): adding
  adapters legitimately moves those assertions to the new source of truth —
  never skip, xfail, weaken, or delete an assertion. Parser preflight and capture
  counts must grow exactly with each new adapter.
- `ci-artifacts-*/` directories are gitignored local scratch (downloaded
  evidence). Check `git status` before staging; never commit artifacts.
- The docker-verification workflow runs on docs-only pushes too (~17–40 min) —
  batch docs edits to save cycles.
- Evidence files to copy per run: `ci-parser-preflight.txt`, `pytest-summary.json`,
  `docker-integration/capture.log`, `storage-conformance.json`,
  `docker-integration/egress-scenario.json`, `image-ids-and-dockerfile-sha256.txt`.
- This `gh` version has no `run view --json artifacts` field — use
  `gh api repos/frostknightfrosty-lgtm/aletheia/actions/runs/<id>/artifacts`.
- Local suite skips are environment-only: 60 docker tests + 5 storage-service
  tests skip without Docker/services on this machine; CI fails if either group
  skips. Local consistency check: `passed + skipped == CI passed`.
- Point-in-time documents stay unedited: `audit/CLAIMS_VS_VERIFIED_AUDIT.md`,
  `aletheia_step3_CI_READY.md`, old logs. This log + HANDOFF supersede them.

## Queue

### Track 1 — Phase 17 cascade engine (`docs/PIVOT_CASCADE.md` §15)
- [x] **P17.2** — cascade models + descriptor-derived routing graph + coverage
      invariant tests + seed autodetection (+ multi-seed wiring: reuse Phase 16
      `pending_seeds`, `<adapter>@seedN` workspaces, `seed_index` provenance,
      5% intersection boost that never creates a candidate, ContextFilters).
      → Implemented locally-green; pushed `7900ce4`; run `39153749577`
      **green** — evidence lines copied to the Log (parser 49/49; 815 passed;
      capture 60/60; storage 6/6).
- [x] **P17.3** — claim normalization + blocking + pivot extractors + fixtures.
      → Implemented locally-green (25 tests); pushed `d7f035a`; run
      `39154364738` **green** — evidence lines copied to the Log (parser
      49/49; 840 passed; capture 60/60; storage 6/6).
- [x] **P17.4** — matchers, perceptual hashing, LR scoring, base-rate priors,
      calibration hook (Platt/isotonic in `core/calibration.py` stays the only
      probability path; an untrained model is never presented as a probability).
      → Implemented locally-green (56 tests; local 831 passed + 65 skips →
      expected CI 896); pushed `db5f03e`; run `39155284979` **green** —
      evidence lines copied to the Log (parser 49/49; 896 passed; capture
      60/60; storage 6/6).
- [ ] **P17.5** — falsification pass + ACH + union-find conflict propagation.
      → Implemented locally-green (26 tests; local 857 passed + 65 skips →
      expected CI 922); pushed `d561c9c`; run verifying.
      Notes: source-grade plumbing — the E/F low-grade gate cap mechanism
      landed in `scoring.py`; wiring `Claim.source_grade` into evidence items
      is deferred until a grading pass assigns real grades (F6-unrated stays
      "not yet graded"; §17 resolution item 7).
- [ ] **P17.6** — VOI scheduler + adaptive budgets + stop policy + resume +
      decision ledger.
      → Implemented locally-green (22 tests; local 879 passed + 65 skips →
      expected CI 944); pushed `341f055`; run verifying.
- [ ] **P17.7** — case memory + cache/TTL + re-audit diffs.
- [ ] **P17.8** — CLI + trail/dossier/coverage outputs + next-actions checklist +
      redaction/purge (no new adapters in this step).
- [ ] **P17.9** — synthetic worlds + adversarial + failure-injection suites in CI.
- [ ] **P17.10** — fixture dry-run → local suite → CI → live cascade on
      `username:frost2233` (authorization on file). Owner confirmations and the
      first real calibration labels are owner-gated — park them.

### Track 2 — Source completeness (`docs/SOURCE_COMPLETENESS.md`; P17.11–P17.12)

Item numbers below are §A rows unless marked §B. Each wave is its own
verification unit; keyed sources are built now with recorded skip paths that
activate when the key exists.

- [ ] **Wave A — keyless/offline builds:** §A 2 (Zehef), 3 (scrawler subset or
      evidenced blocker), 4 (tiktok-hashtag-analysis), 11 (Bron Vault local-log
      parser), 12 (VENOM), 13 (PicImageSearch — free engines only), 14
      (tracelines), 15 (ShadowFinder), 16 (pybdshadow), 18 (GeoLocator), 20
      (crypttrace CLI wrap), 27 (ERATV SPARQL), 31 (SearXNG self-hosted
      container), 33 (Unpaywall DOI endpoint), 36 (CipherScan pinned by commit);
      re-check-with-evidence §A 28 (PatentsView), 29 (Google Patents BigQuery),
      32 (Google CSE), 35 (PublicWWW); §B Blackbird (license resolved first),
      Lullar, paste indexes, reverse-image free engines, people-search free
      tiers, face-search free engines, bulk/paste handling rules.
- [ ] **Wave B — free-registration/keyed builds (skip paths recorded):** §A 1
      (OWASP SocialOSINTLM), 8 (Intelligence X), 9 (BreachDirectory), 10
      (Leak-Lookup), 17 (youtube-geofind), 19 (Betaface), 30 (EUIPO), 34
      (GitLab); §B LeakCheck, LeakRadar, OsintCat, OathNet, Hudson Rock, GHunt.
- [ ] **Wave C — darkweb_search behind container-level Tor:** §A 5 (OnionSearch),
      6 (TorBot), 7 (Piano); §B 13 (Ahmia / Torch / OnionLand / DarkSearch
      per-engine notes; recorded ToS risk posture).
- [ ] **Wave D — transport_movement:** §A 22 (OpenSky), 23 (BarentsWatch), 24
      (Network Rail), 25 (National Rail), 26 (Deutsche Bahn).
- [ ] **Wave E — P17.12 completeness verification:** per-source evidence from
      artifacts; live coverage only where gates permit. §A 21 (FollowTheMoney)
      stays blocked at Gate 7.

### Track 3 — Horizon completion
- [x] Recorded as **P17.13** in `docs/PIVOT_CASCADE.md` §15 item 13 (2026-10-18,
      campaign); adopted defaults recorded in §17 the same day.
- [ ] Build, interleaved with Track 2 whenever no completeness item is locally
      unblocked: Wayback CDX; Wikidata/ORCID; keyservers (WKD / GitHub `.keys`);
      GitHub endpoints expansion; Mojang/NameMC; WhatsMyName; social-graph
      lists; Phase 9 residuals (news_search, Open-Meteo, historical).

### Track 4 — Close-out
- [ ] Final full verification pass on the final tree; copy all evidence lines.
- [ ] Finalize `docs/USER_ACTIONS.md`: exact key names, signup URLs actually used
      in reviews, secret names, what each unlocks.
- [ ] Final `RESUME_STATE.json` + `HANDOFF.md`; final report in chat for the owner.

## Log

<!-- append-only; newest last. Format: date — item — commit — run — copied evidence — next -->

- 2026-10-18 — Campaign staged: anchors written (`docs/CAMPAIGN_LOG.md`,
  `docs/USER_ACTIONS.md`, `RESUME_STATE.json`, `HANDOFF.md`). Prep push next;
  verify its run, then start P17.2.
- 2026-10-18 — Prep commit `e8ce609` (docs + state anchors) — run
  `39152717185` — docker-verification **green** (15m34s). Copied from the
  downloaded artifact `ci-artifacts-39152717185`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "786 passed, 1 warning"`,
    `"junit_total": 786`, `"skipped_in_ci": []`, `"ok": true`
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.2 implemented (cascade models in `core/models.py`; new
  `aletheia/cascade/` package: `routing.py` descriptor-derived graph +
  coverage validators, `seeds.py` autodetection/canonicalization/dedup;
  29 new tests). Local suite: 750 passed + 65 environment-only skips
  (expected CI passed count: 815). Pushed as `7900ce4`; verification run
  `39153749577` in flight — evidence lines to be appended when the artifact
  is downloaded.
- 2026-10-18 — P17.2 verification — commit `7900ce4` — run `39153749577` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39153749577`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "815 passed, 1 warning"`,
    `"junit_total": 815`, `"skipped_in_ci": []`, `"ok": true`
    (786 → 815: the 29 new cascade tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.3 implemented (claim layer + pivot extractors + 25 tests;
  local suite 775 passed + 65 environment-only skips → expected CI 840) and
  pushed as `d7f035a` (docs commit `e86a042` adds the adopted defaults,
  P17.13's recording, and prep-run evidence). Verification run
  `39154364738` watching in the background.
- 2026-10-18 — P17.3 verification — commit `d7f035a` — run `39154364738` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39154364738`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "840 passed, 1 warning"`,
    `"junit_total": 840`, `"skipped_in_ci": []`, `"ok": true`
    (815 → 840: the 25 new claim/extractor tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.4 implemented (matchers incl. NARA-vector Soundex and
  nickname expansion; stdlib PNG/BMP/PPM decode + aHash/dHash/DCT pHash with
  Pillow fallback; LR scoring with review-gate cap; base-rate priors;
  calibration hook; claim-pair evidence table; 56 tests; local 831 passed +
  65 environment-only skips → expected CI 896) and pushed as `db5f03e`
  (docs commit `91e36cb` copies the P17.2 verification evidence). Verification
  run `39155284979` watching in the background.
- 2026-10-18 — P17.4 verification — commit `db5f03e` — run `39155284979` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39155284979`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "896 passed, 1 warning"`,
    `"junit_total": 896`, `"skipped_in_ci": []`, `"ok": true`
    (840 → 896: the 56 new matcher/pHash/scoring/evidence tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.5 implemented (falsification pass, ACH hypothesis scoring
  with the conservative tie order, union-find merge graph with conflict
  propagation, low-grade E/F gate cap; 26 tests; local 857 passed + 65
  environment-only skips → expected CI 922) and pushed as `d561c9c` (docs
  commit `051625c` copies the P17.3 verification evidence and records the
  source-grade resolution). Verification run `39156241115` watching in the
  background.
- 2026-10-18 — P17.6 implemented (VOI scheduler with the section-8 formula and
  clamped cost, per-type caps, depth escalation only in owner mode with HARD
  evidence, time-pressure de-escalation, stop-policy derivation, JSON-safe
  resume checkpoints, hash-chained decision ledger; 22 tests; local 879 passed
  + 65 environment-only skips → expected CI 944) and pushed as `341f055`.
  Verification run starting.
- Next: start P17.7 (case memory + cache/TTL + re-audit diffs) locally; on
  `39156241115` green copy P17.5 evidence; on `341f055`'s run green copy P17.6
  evidence.
