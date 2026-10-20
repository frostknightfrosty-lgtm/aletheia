# Phase 17 close-out report (P17.11–P17.13)

Date: 2026-10-20 (UTC). This report is standalone: every CI number below is
copied from a downloaded Docker Verification artifact, never retyped from a
plan or transcript.

## Outcome

- **P17.11 / P17.12 are closed.** The tracker records **83 of 111 accepted
  sources wired** and **28 remaining**, each with a written owner-gate, upstream
  blocker, or documented drop in `docs/COMPLETENESS_AUDIT.md` and
  `docs/SOURCE_COMPLETENESS.md`.
- **P17.13 is complete for every adoptable free/public source.** Five new units
  were built, reviewed, and CI-verified: `researcher_ids`, `weather`,
  `github_identity`, `pgp_keys`, and `minecraft`.
- The tree now has **62 registered adapters**, **65 manifest entries** (the 62
  adapters plus `egress_proxy` and two Python libraries), and **55
  network-required adapters** wired by the egress policy. All 62 adapters are
  `verified-fixture`; there is no `unknown` or `pending` adapter.
- NameMC, social-graph list ingestion, and `news_search` are **written
  exclusions**, not silent gaps. See `docs/NOT_INTEGRATED.md`.
- The only live authorization on file remains `username:frost2233`. All five
  new P17.13 units are fixture-only; no live source lookup was performed for
  them.

## Evidence table

| Unit | Code commit | Docker Verification run | Parser | Tests | Capture | Egress | Storage |
|---|---|---|---|---|---|---|---|
| `researcher_ids` | `ceaf595` | `39484536317` | 58/58 | 1141 passed | 84/84 | 58/51/51 | 6/6 |
| `weather` | `503b431` | `39487437707` | 59/59 | 1149 passed | 87/87 | 59/52/52 | 6/6 |
| `github_identity` | `58aa354` | `39493701837` | 60/60 | 1158 passed | 90/90 | 60/53/53 | 6/6 |
| `pgp_keys` | `82a4049` | `39494804791` | 61/61 | 1167 passed | 93/93 | 61/54/54 | 6/6 |
| `minecraft` | `9c9cd9c` | `39495727637` | 62/62 | 1175 passed | 96/96 | 62/55/55 | 6/6 |

All five runs report `skipped_in_ci: []` and `ok: true`. Each egress row also
reports `wired` equal to `network_required`; each capture result set contains
the expected number of entries with **0 nonzero return codes**.

The researcher/weather documentation tree was separately verified by run
`39491992247` on commit `590414a`: parser 59/59; 1149 passed; capture 87/87;
egress 59/52/52; storage 6/6; 87 results, 0 nonzero.

## What each new unit does

- **`researcher_ids`** — one composite adapter over the keyless Wikidata Action
  API and ORCID public API v3.0. One bounded name query per source, at most five
  results per source; ORCID `email` arrays are discarded. Name matches are
  leads, not identity proof (0.2 run / 0.4 result confidence).
- **`weather`** — one adapter over Open-Meteo forecast current/daily and the
  historical archive. The `GEOLOCATION` seed is `lat,lon` or
  `lat,lon,YYYY-MM-DD`; one request per run; non-commercial free-API limits
  recorded; CC-BY 4.0 attribution retained. Environmental context only, 0.8
  confidence.
- **`github_identity`** — six unauthenticated public reads per run: profile,
  latest repositories, gists, public events, API SSH keys, and
  `github.com/<user>.keys`. The 60 requests/hour unauthenticated quota is
  documented; profile email is deliberately dropped; event/gist contents are
  not fetched; SSH keys are reduced to OpenSSH SHA-256 fingerprints. This
  covers the GitHub half of the P17.13 keyserver item and the GitHub endpoint
  expansion.
- **`pgp_keys`** — one email-seeded WKD lookup: advanced method first, direct
  method only on a DNS failure as the specification requires. Standard-library
  OpenPGP parsing; only matching User IDs retained; fingerprints/key metadata
  only, never key material; no Authorization header. This covers the WKD half of
  the keyserver item.
- **`minecraft`** — current Mojang Java profile and public session texture
  metadata; at most two unauthenticated GETs per run; current handle, UUID,
  public skin/cape URLs, and skin model only. NameMC and the removed name-history
  endpoint are excluded.

## Written exclusions and remaining limits

- **NameMC** — no public API and site terms do not authorize scraping. The free
  Mojang current-profile API is implemented; NameMC history is not fetched.
- **Social-graph list ingestion** — already covered in substance by the pinned
  maigret/sherlock site enumeration in `social_username`; a duplicate list
  adapter is not justified.
- **`news_search`** — GDELT's DOC endpoint rejects the descriptive
  `Aletheia/0.1` User-Agent with its rate-limit message; public Google/Bing RSS
  endpoints have no automated-search API contract; keyed news APIs are Gate 3
  owner registrations. The item is parked rather than implemented by
  impersonating a User-Agent or scraping a page.
- **Owner-gated work** — Wave B (free registration/keyed sources), Wave C
  (darkweb behind container-level Tor), and Wave D (transport APIs) remain in
  `docs/USER_ACTIONS.md`. No account or key was registered on the owner's
  behalf, and no secret was added to the repository.
- **Other recorded drops** remain as recorded in `docs/NOT_INTEGRATED.md`
  (`scrawler`, `GeoLocator`, ERATV, PatentsView legacy host, Google CSE,
  PublicWWW, Blackbird/Lullar/people-search/face-search limits, and the
  FollowTheMoney Gate 7 exclusion).

## Final local verification and hygiene

- Local full suite at the final code tree: **1097 passed + 78 skipped = 1175**,
  matching the CI passed count exactly. The 78 skips are 73 Docker-dependent
  tests (no Docker locally) plus the 5 storage-service tests; both groups
  execute in CI.
- Parser pre-flight locally: **62/62**.
- `PROJECT_MANIFEST.json` parses; **65 entries**, **63 `verified-fixture`**
  (62 adapters + `egress_proxy`), and **2 `verified-source-read`** libraries.
- Point-in-time `ci-*` directories are downloaded evidence and are never
  committed. `RESUME_STATE.json` remains LF-only with no BOM.
- Code, docs, and state are committed separately and pushed directly to
  `main`; no PR, force-push, amend, or history rewrite was used.

## Bottom line

P17.11 and P17.12 are closed and evidenced. P17.13's free/public horizon is
closed with five new verified units and three written exclusions. The next work
is owner-gated: keys/registrations, optional verified-live promotion, Tor-backed
engines, and transport APIs.
