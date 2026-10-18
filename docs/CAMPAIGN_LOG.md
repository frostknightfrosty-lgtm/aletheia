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
- Position: **P17.10 complete** — CI green (run `39159820872`; 1005 passed),
  repair verified (run `39161437568`; 1011 passed), and the live cascade
  **green** (run `39161463451`, tree `9a9cb38`: `stop_reason=saturated`,
  `expansions=1`, `trail_digest=f2af6529…`, `coverage_ok=True`,
  `manifest anchor: verified`; instaloader blocked ×2 and recorded — the
  failure class the repair targeted is closed). **P17.11 Wave A**: re-checks
  recorded; §A 33 (Unpaywall) CI-verified and flipped; §A 31 (SearXNG)
  CI-verified and flipped; §A 36 (CipherScan) and §A 11 (Bron Vault) units
  pushed — runs in flight.
  **P17.3–P17.10 verified green.**
- Next action: on the CipherScan run (`39167510546`, head `f785aa7`) and the
  Bron Vault run (`39168364470`, head `d3e7d16`) green: copy lines, flip §A 36
  and §A 11, update the `ssl_tls` / `leak_checkers` manifest entries; then the
  rest of the Wave A list (Zehef, scrawler, tiktok-hashtag-analysis, VENOM,
  PicImageSearch, tracelines, ShadowFinder, pybdshadow, GeoLocator, crypttrace
  CLI wrap, ERATV, BigQuery), then Waves B–E.
- In-flight CI: `39167510546` (CipherScan, expected 1030 passed / capture
  62/62); `39168364470` (Bron Vault, expected 1034 passed / capture 63/63).
- Last verified commit: `1c18b80` (run `39166656036`; parser 49/49;
  **1021 passed**; capture 61/61; storage 6/6).
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
- [x] **P17.5** — falsification pass + ACH + union-find conflict propagation.
      → Implemented locally-green (26 tests; local 857 passed + 65 skips →
      expected CI 922); pushed `d561c9c`; run `39156241115` **green** —
      evidence lines copied to the Log (parser 49/49; 922 passed; capture
      60/60; storage 6/6).
      Notes: source-grade plumbing — the E/F low-grade gate cap mechanism
      landed in `scoring.py`; wiring `Claim.source_grade` into evidence items
      is deferred until a grading pass assigns real grades (F6-unrated stays
      "not yet graded"; §17 resolution item 7).
- [x] **P17.6** — VOI scheduler + adaptive budgets + stop policy + resume +
      decision ledger.
      → Implemented locally-green (22 tests; local 879 passed + 65 skips →
      expected CI 944); pushed `341f055`; run `39156855944` **green** —
      evidence lines copied to the Log (parser 49/49; 944 passed; capture
      60/60; storage 6/6).
- [x] **P17.7** — case memory + cache/TTL + re-audit diffs.
      → Implemented locally-green (case store with snapshots/timeline/diffs,
      source cache with TTL classes and scheduler-parity freshness, label
      store feeding the calibrator, blind-spot registry; 24 tests; local 903
      passed + 65 skips → expected CI 968); pushed `60bb0e6`; run
      `39157495630` **green** — evidence lines copied to the Log (parser
      49/49; 968 passed; capture 60/60; storage 6/6).
- [x] **P17.8** — CLI + trail/dossier/coverage outputs + next-actions checklist +
      redaction/purge (no new adapters in this step).
      → Implemented locally-green (cascade CLI group review/confirm/purge;
      trail/dossier/coverage builders; next-actions checklist; deterministic
      redaction; 21 tests; local 924 passed + 65 skips → expected CI 989);
      pushed `ced6f08`; run `39158143846` **green** — evidence lines copied
      to the Log (parser 49/49; 989 passed; capture 60/60; storage 6/6).
- [ ] **P17.9** — synthetic worlds + adversarial + failure-injection suites in CI.
      → Implemented locally-green (`cascade/engine.py`: deterministic engine
      over an injectable observer — gated pivots, VOI scheduling,
      falsification-first merges, per-origin claim independence, parent-linked
      trail + hash-chained ledger; synthetic worlds, adversarial collisions,
      blocked/429 + budget + hard-depth failure injection, golden-digest
      determinism; 9 tests; local 933 passed + 65 skips → expected CI 998);
      pushed `e9b8de5`; run `39159218589` **green** — evidence lines copied
      to the Log (parser 49/49; 998 passed; capture 60/60; storage 6/6).
- [x] **P17.10** — fixture dry-run → local suite → CI → live cascade on
      `username:frost2233` (authorization on file). Owner confirmations and the
      first real calibration labels are owner-gated — parked (one cluster now
      awaiting confirmation; `USER_ACTIONS.md` §3).
      → CI green: pushed `dc44fc5` + docs `39680b0`; run `39159820872`
      **green** — parser 49/49; 1005 passed; capture 60/60; storage 6/6 (lines
      copied to the Log). First live dispatch (run `39159843080`) **failed in
      the wiring**: instaloader timed out (recorded) and the next instaloader
      invocation collided with the leftover per-invocation Docker network
      (`docker network create --internal aletheia-egress-net-instaloader` →
      "already exists"), crashing outside the per-adapter error handling.
      Repair `708ad27`: one egress session per adapter per run (network names
      are adapter-derived), incremental chaining, start failures recorded and
      never run unwired, `close()` teardown — repair verified by run
      `39161437568` **green** (parser 49/49; **1011 passed**; capture 60/60;
      storage 6/6). **Live cascade green**: run `39161463451` on the repaired
      tree `9a9cb38` — `stop_reason=saturated`; `expansions=1`;
      `trail_digest=f2af6529df6125190d1b88994be038b941b60459dcd2598bd88a511ff60c0247`;
      `coverage_ok=True`; `verify-chain.log` `valid` + `chain tip
      feaad1a7811bedd9b0a917f05dbe776388bcfe85542d3d6d44be80cd626b5edc` +
      `manifest anchor: verified`. 6/7 expected adapters ran; instaloader
      blocked ×2 and recorded (`cascade_adapter_error x2`) — the exact failure
      class the repair closed; `egress_request x1146`. 1 identity cluster
      awaits owner confirmation (parked). Lines copied to the Log.

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
      → Progress: the re-check-with-evidence items are recorded in
      `docs/PHASE17_RECHECKS.md` (2026-10-18): 28 legacy host dead /
      successor behind a USPTO account; 29 sandbox no-billing route exists
      (build queued; owner token); 32 closed notice stands — Marginalia +
      Common Crawl carry the class; 35 no free tier surfaced; 27 no public
      SPARQL/RDF (NXDOMAIN + browser-only app). §A 33 (Unpaywall DOI route)
      **CI-verified**: run `39160798771` — parser 49/49; 1009 passed; capture
      60/60; storage ok (lines in the Log); §A 33 flipped. §A 31 (SearXNG)
      **CI-verified**: run `39166656036` — parser 49/49; 1021 passed; capture
      61/61; storage 6/6; §A 31 flipped and the `search_engines` manifest
      entry updated. §A 36 (CipherScan) and §A 11 (Bron Vault) built and
      pushed (`f785aa7`, `d3e7d16`) — runs in flight.
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
- 2026-10-18 — P17.7 implemented (subject-centric case store with snapshots,
  timeline, and re-audit diffs; cross-run source cache with per-source TTLs —
  30d profiles / 7d DNS adopted, 7d configuration provisional — and
  scheduler-parity freshness; confirmation label store whose training pairs
  feed `core/calibration.py` (unsure and scoreless labels excluded);
  blind-spot registry with cited curated limits and an observed-limits store;
  24 tests; local 903 passed + 65 environment-only skips → expected CI 968)
  and pushed as `60bb0e6`.
  Observation (pre-existing, not P17.7 scope): the Phase-13 Platt fit
  diverges on a perfectly separable small sample (decision boundary lands far
  left of the data; every prediction saturates at 1.0). Real calibration data
  overlaps, where the fit converges — noted for future calibration work.
- 2026-10-18 — P17.5 verification — commit `d561c9c` — run `39156241115` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39156241115`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "922 passed, 1 warning"`,
    `"junit_total": 922`, `"skipped_in_ci": []`, `"ok": true`
    (896 → 922: the 26 new falsification/ACH/merge-graph tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.8 implemented (cascade CLI group: `review` replays a
  decision ledger and verifies its hash chain, `confirm` records
  mine/not-mine/unsure labels with the cluster's recorded score, `purge`
  deletes a case file and its labels; `trail.py` parent-linked trail builder
  with the golden `trail_digest`; `dossier.py` tiered dossier builder that
  flags unsupported fields instead of inventing evidence; `coverage.py` audit
  with the design's end-of-run assertion; `next_actions.py` checklist copied
  from USER_ACTIONS.md; `redact.py` deterministic person-identifier tokens;
  21 tests; local 924 passed + 65 environment-only skips → expected CI 989)
  and pushed as `ced6f08`.
- 2026-10-18 — P17.6 verification — commit `341f055` — run `39156855944` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39156855944`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "944 passed, 1 warning"`,
    `"junit_total": 944`, `"skipped_in_ci": []`, `"ok": true`
    (922 → 944: the 22 new scheduler/ledger tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.7 verification — commit `60bb0e6` — run `39157495630` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39157495630`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "968 passed, 1 warning"`,
    `"junit_total": 968`, `"skipped_in_ci": []`, `"ok": true`
    (944 → 968: the 24 case-memory/cache/label/blind-spot tests, none
    skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.9 implemented — `e9b8de5` — deterministic cascade engine
  (`app/aletheia/cascade/engine.py`) over the injectable observer boundary
  `Callable[[Seed], Observation]`; anchors are the subject by construction,
  every other claim compares only through P17.3 blocking, a merge requires
  the P17.4 confirmed tier **and** ACH `H_subject` survival, vetoes exclude
  before evidence is summed, gated pivots are recorded (`pivot_gated`), and
  stops latch through the P17.6 scheduler. Composition facts pinned by the
  suites (v1 reachability): identical values from independent origins reach
  HARD/STRONG (echo evidence), domain bridges reach MEDIUM/WEAK, and
  name-class support cannot chain (identical-key blocking); an accepted
  claim's own pivots are same-value duplicates, so deep fresh expansions are
  the exception, not the rule — the hard-depth refusal path is tested
  explicitly. 9 new tests; local 933 passed + 65 environment-only skips →
  expected CI 998; pushed; run starting.
- 2026-10-18 — P17.8 verification — commit `ced6f08` — run `39158143846` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39158143846`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "989 passed, 1 warning"`,
    `"junit_total": 989`, `"skipped_in_ci": []`, `"ok": true`
    (968 → 989: the 21 cascade CLI/artifact/redaction tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.10 implemented — `dc44fc5` — cascade run wiring:
  `cascade/runner.py` builds one audited run per cascade (verbatim
  authorization assertion + scheduler checkpoint on the manifest), runs the
  engine over either the pure fixture observer (CI dry-run; no I/O at all)
  or the live `AdapterObserver` (one invocation per supporting adapter,
  egress proxied and chain-appended, failures recorded as blocked hops,
  skip records kept out of the claims), then writes ledger/trail/dossier/
  coverage/next-actions artifacts, asserts the coverage audit, and
  optionally records the run on a case. `aletheia cascade run` wires it into
  the CLI; `.github/workflows/live-cascade.yml` is the dispatch path for
  authorized live runs. 7 new runner tests; local 940 passed + 65
  environment-only skips → expected CI 1005; pushed; run starting. Live
  dispatch for `username:frost2233` (Gate 2 assertion verbatim) happens when
  this run is green.
- 2026-10-18 — P17.9 verification — commit `e9b8de5` — run `39159218589` —
  docker-verification **green**. Copied from the downloaded artifact
  `ci-artifacts-39159218589`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "998 passed, 1 warning"`,
    `"junit_total": 998`, `"skipped_in_ci": []`, `"ok": true`
    (989 → 998: the 9 cascade engine tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — P17.11 Wave A (part 1) — re-checks recorded in
  `docs/PHASE17_RECHECKS.md` (#28 PatentsView: legacy host NXDOMAIN, USPTO
  portal successor; #27 ERATV: NXDOMAIN + browser-only; #29 BigQuery
  sandbox no-billing route; #32 Google CSE: closed notice stands; #35
  PublicWWW: no free tier; #33 Unpaywall: DOI endpoint live, email
  enforced). §A 33 built: `docker/academic_search/runner.py` gains the
  DOI-keyed live path (`GET /v2/{doi}` with `UNPAYWALL_EMAIL`), the adapter
  parses DOI records (`unpaywall_doi_record`), `UNPAYWALL_EMAIL` joins
  `secret_env` and both live workflows, RATE_LIMITS.md re-annotated; 4 new
  tests; local 944 passed + 65 environment-only skips → expected CI 1009;
  pushed; run verifying.
- 2026-10-18 — P17.10 CI verification — commit `dc44fc5` (docs `39680b0`) —
  run `39159820872` — docker-verification **green**. Copied from the
  downloaded artifact `ci-artifacts-39159820872`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "1005 passed, 1 warning"`,
    `"junit_total": 1005`, `"skipped_in_ci": []`, `"ok": true`
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`
  - storage-conformance.json: `"passing": ["file", "postgres", "neo4j",
    "elasticsearch", "minio", "redis"]`, `"unconfigured": []`,
    `"required_all": true`, `"ok": true`
- 2026-10-18 — live cascade incident (first dispatch, run `39159843080`) —
  the run failed outside the per-adapter error handling. Copied from the
  artifact `ci-live-cascade-39159843080` (`cascade.log` tail):
  - `aletheia.core.egress.DockerCommandError: wiring command failed (exit 1):
    docker network create --internal aletheia-egress-net-instaloader`
  - `Error response from daemon: network with name
    aletheia-egress-net-instaloader already exists`
  AUDIT.jsonl: `adapter_invocation x8`, `adapter_complete x6`,
  `cascade_adapter_error x1` — instaloader `container timed out after 120s`
  (recorded); leak_checkers/maigret/reddit-api/sherlock/social_username/
  youtube-api completed; a later instaloader pivot then collided with the
  timed-out invocation's leftover network. Root cause: per-invocation
  `egress.ProxySession` with an adapter-derived network name, and
  `session.start()` outside the recorded-error try. Repair: one session per
  adapter per run + incremental chaining + recorded start failures +
  `close()` teardown; 2 regression tests; local `946 passed + 65 skips →
  expected CI 1011`.
- 2026-10-18 — P17.11 Unpaywall verification — commit `dfd8f0a` (docs
  `139d141`) — run `39160798771` — docker-verification **green**. Copied
  from the downloaded artifact `ci-artifacts-39160798771`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "1009 passed, 1 warning"`,
    `"junit_total": 1009`, `"skipped_in_ci": []`, `"ok": true` (1005 → 1009:
    the 4 Unpaywall tests, none skipped)
  - docker-integration/capture.log: `DOCKER CAPTURE: PASS — 60/60 cases
    captured`; storage-conformance.json: `"required_all": true`,
    `"ok": true`, `"unconfigured": []`
  §A 33 flipped in `SOURCE_COMPLETENESS.md`.
- 2026-10-18 — P17.10 live cascade verification — repair commit `708ad27`
  (docs `9a9cb38`) — repair run `39161437568` docker-verification **green**.
  Copied from `ci-artifacts-39161437568`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "1011 passed, 1 warning"`,
    `"junit_total": 1011`, `"skipped_in_ci": []`, `"ok": true`
  - `DOCKER CAPTURE: PASS — 60/60 cases captured`; storage-conformance.json:
    `"required_all": true`, `"ok": true`, `"unconfigured": []`
  Live cascade re-dispatch (same tree `9a9cb38`) — run `39161463451` —
  **green** (`conclusion: success`). Copied from the artifact
  `ci-live-cascade-39161463451`:
  - `cascade.log` tail: `run: e86fefe0-ff40-4c98-b7e8-9d846b59460b`;
    `stop_reason=saturated`; `expansions=1`;
    `trail_digest=f2af6529df6125190d1b88994be038b941b60459dcd2598bd88a511ff60c0247`;
    `coverage_ok=True`
  - `verify-chain.log`: `valid: e86fefe0-ff40-4c98-b7e8-9d846b59460b`;
    `chain tip: feaad1a7811bedd9b0a917f05dbe776388bcfe85542d3d6d44be80cd626b5edc`;
    `manifest anchor: verified`
  - `MANIFEST.json` cascade section: `"mode": "live"`, `"coverage_ok": true`,
    `"expansions": 1`, `"stop_reason": "saturated"`,
    `"authorization_assertion"` carries the Gate 2 text verbatim; scheduler
    checkpoint `{"checkpoint_version": 1, ..., "saturated": true,
    "used_by_type": {"username": 1}}`; `chain_tip` present
  - `coverage.json`: 7 adapters expected, 6 ran — instaloader
    `"blocked: container…"` recorded; documented skips
    (breachdirectory / bron-vault / grayhatwarfare) unchanged
  - `AUDIT.jsonl`: `cascade_run_started x1`, `adapter_invocation x16`,
    `adapter_complete x12`, `cascade_adapter_error x2` (instaloader timeout,
    both rounds — recorded; run survived), `egress_request x1146`,
    `cascade_run_finished x1`
  - expansions `0002–0007` + `0009–0014` (second pass reused the per-adapter
    egress sessions — no collision; the first dispatch's failure class)
  - `next_actions.json`: free keys (already parked in `USER_ACTIONS.md`);
    provider permissions (OpenSky, EUIPO — parked); 1 identity cluster
    awaiting owner confirmation (`4bb198ed-daa5-4412-a1cc-dbd34872e7bb`)
  Docs run `39162358358` (tree `fe5fc7f`) **green** — parser 49/49; 1011
  passed; capture 60/60; storage 6/6.
- Next: continue P17.11 Wave A builds (SearXNG self-hosted container,
  CipherScan pinned commit `30bd2393`, Bron Vault offline parser); on this
  push's run green copy its lines; then the rest of the queue.
- 2026-10-19 — docs/state push verification — commits `d436593` (docs) +
  `ac68b89` (state) — run `39165890328` — docker-verification **green**.
  Copied from the downloaded artifact `ci-artifacts-39165890328`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "1011 passed, 1 warning"`,
    `"junit_total": 1011`, `"skipped_in_ci": []`, `"ok": true`
  - `DOCKER CAPTURE: PASS — 60/60 cases captured`; storage-conformance.json:
    `"required_all": true`, `"ok": true`, `"unconfigured": []` (6/6 backends
    passing)
- 2026-10-19 — P17.11 SearXNG verification — commit `1c18b80` — run
  `39166656036` — docker-verification **green**. Copied from the downloaded
  artifact `ci-artifacts-39166656036`:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - pytest-summary.json: `"console_summary": "1021 passed, 1 warning"`,
    `"junit_total": 1021`, `"skipped_in_ci": []`, `"ok": true` (1011 → 1021:
    the 10 SearXNG tests, none skipped)
  - `DOCKER CAPTURE: PASS — 61/61 cases captured` (new case
    `phase17-search-engines-searxng` runs the offline selftest under
    `--network none`); storage-conformance.json: `"required_all": true`,
    `"ok": true`, `"unconfigured": []` (6/6 backends passing)
  §A 31 flipped in `SOURCE_COMPLETENESS.md`; `search_engines` manifest entry
  updated (three sub-sources; searxng removed from the dropped list).
- Next: on the CipherScan run (`39167510546`, head `f785aa7`) and the Bron
  Vault run (`39168364470`, head `d3e7d16`) green: copy lines, flip §A 36 and
  §A 11, update the `ssl_tls` / `leak_checkers` manifest entries; then the
  rest of the Wave A list.
