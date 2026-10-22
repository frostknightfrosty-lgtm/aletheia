# User Actions — the only items reserved for the owner

> **Everything else is handled autonomously.** The campaign (`docs/CAMPAIGN_LOG.md`)
> builds, wires, and CI-verifies every free, open path on its own. This file lists —
> and nothing else — the items that genuinely require the owner. It is kept current;
> when the campaign stops, this file is the complete remainder.
>
> All items are free. Nothing here requires payment, and nothing paid will ever be
> adopted. Keyed sources are already built with recorded skip paths, so most of
> these convert a recorded skip into live coverage the moment the key exists.

## 0. CI capacity (resolved 2026-10-20)

The repository was made public on 2026-10-20 (verified `private: false`), so
standard GitHub-hosted runners are free and CI resumed. The blocked tracelines
run then executed and exposed a real image defect (Python 3.11 could not install
`networkx==3.7`); fixed on Python 3.12 and verified green in run `39416003189`.
No payment was involved and no action remains. This section is kept as a
record.

## 1. Free API keys (Gate 3) — register, then store as GitHub Secrets

Last verified: 2026-10-22. Secret values are stored only in GitHub Actions
secrets and the local DPAPI store; they are never committed.

How: repo → **Settings → Secrets and variables → Actions → New repository secret**
(`frostknightfrosty-lgtm/aletheia`). The campaign records the exact env-var name and
the signup URL actually used during each scoped review (never guessed).

Configured and directly verified:

- [x] **LeakIX** — live `leak_checkers` path — secret `LEAKIX_API_KEY` — direct API HTTP 200 (2026-10-20)
- [x] **IPGeolocation.io** — `ip_intelligence` path — secret `IPGEOLOCATION_KEY` — direct API HTTP 200 (2026-10-20)
- [x] **GrayhatWarfare** — live `leak_checkers` path — secret `GRAYHATWARFARE_TOKEN` — direct API HTTP 200 with the honest Aletheia user agent (2026-10-22)
- [x] **AbuseIPDB** — `ip_intelligence` path — secret `ABUSEIPDB_KEY` — direct API HTTP 200 (2026-10-22)
- [x] **Netlas** — `ip_intelligence` path — secret `NETLAS_KEY` — direct API HTTP 200 with the honest Aletheia user agent (2026-10-22)
- [x] **SauceNAO** — `picimagesearch` optional path — secret `SAUCENAO_API_KEY` — file-upload API HTTP 200 (2026-10-22); URL-fetch mode may hit Cloudflare
- [x] **YouTube Data API** — `youtube-api` adapter + `youtube-geofind` — secret `YOUTUBE_API_KEY` — direct API HTTP 200 (2026-10-22)
- [x] **abuse.ch** — `ip_intelligence` URLhaus / ThreatFox / MalwareBazaar — secrets `URLHAUS_AUTH_KEY`, `THREATFOX_AUTH_KEY`, `MALWAREBAZAAR_AUTH_KEY` — all three APIs HTTP 200 (2026-10-22)

**Live workflow validation (2026-10-22).** Live Investigation run
[`39841929311`](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39841929311)
on commit `02c08d5` is green (35m21s) for the owner-asserted
`username:frost2233`. `youtube-api` succeeded (exit 0; two distinct channel
candidates; no missing-key skip) and `leak_checkers` succeeded with LeakIX and
GrayhatWarfare (both `env:` keyed; zero records; no missing-key skips).
`reddit-api` remains the only missing-credential skip. The IP-intelligence,
SauceNAO and abuse.ch keys are wired and direct-verified, but a username-only
seed cannot exercise those paths; no authorized IP or image seed exists. The
first successful keyed run (`39834159214`, 38m28s) exposed LeakIX's `HTTP 204`
empty-response handling; the fix is `02c08d5` and this run is the clean
re-verification.

Closed by owner decision (no action):

- **Reddit** — `reddit-api` adapter — owner decided on 2026-10-22 that Reddit credentials are not needed. The adapter remains a recorded skip; no `REDDIT_CLIENT_ID`/`SECRET` action.

Other source families from the completeness directive (configured entries are
listed above; the rest remain owner-gated or source-blocked):

- **Breach / leak / exposure:** BreachDirectory (RapidAPI free tier), Leak-Lookup,
  LeakCheck (OSINT-Hub free path), Hudson Rock, Intelligence X (`x-key`), abuse.ch
  (URLhaus / ThreatFox / MalwareBazaar Auth-Key), LeakRadar, OsintCat, OathNet.
- **IP intelligence:** IPinfo, IPGeolocation.io, AbuseIPDB, GreyNoise (Community),
  VirusTotal, Netlas, FullHunt, optional PhishTank `app_key`.
- **Corporate / government:** Companies House, KVK, NZBN, ASIC, CIPC, EUIPO
  developer account, `api.data.gov` (FOIA, SAM.gov).
- **Crypto:** Etherscan, Chainabuse.
- **Code / search / academic:** GitLab personal token, Debian Salsa (DCS key),
  Marginalia email key, Semantic Scholar, CORE, EPO OPS (consumer key + secret),
  USPTO Open Data Portal key (PatentsView migration — free account with
  identity fields; request via
  <https://patentsview-support.atlassian.net/servicedesk/customer/portals> or
  the data.uspto.gov portal; the legacy search.patentsview.org host no longer
  resolves).
- **Social / media / misc:** GitHub token, Mapillary, Copernicus Data Space,
  Betaface (key + secret), OWASP SocialOSINTLM platform keys (if its review
  requires them), SauceNAO (`SAUCENAO_API_KEY`; optional — the keyless
  PicImageSearch engines work without it).
- **Transport (Gate 6):** OpenSky (registration **plus written integration
  permission**), BarentsWatch, Network Rail, National Rail, Deutsche Bahn.
- **Telephony (optional):** NumLookupAPI (`numlookupapi.com`) — would enable
  the `phone` path the `venom` adapter intentionally drops (its pinned
  `modules/phone.py` requires a NumLookupAPI key); the signup URL and secret
  name will be recorded at that re-review touch (not guessed here).

Configuration values (no registration, still owner-provided):

- [x] **Unpaywall** — the documented DOI endpoint requires a contact email —
  secret `UNPAYWALL_EMAIL`; configured 2026-10-20 (see `PHASE17_RECHECKS.md` #33).
- [ ] **Broń Vault (optional)** — only if you ever run the Broń Vault stealer-log
  dashboard locally (your own instance; the campaign never deploys or uploads to
  one): set `BRON_VAULT_URL` (a loopback address, e.g. `http://127.0.0.1:3000`)
  + `BRON_VAULT_API_KEY` (created on that instance's API Keys page) to turn the
  documented `leak_checkers` skip into a live local path (see
  `docker/leak_checkers/RATE_LIMITS.md`).
- [ ] **Google Patents (BigQuery)** — sandbox queries need a Google-account
  access token and project — secrets `GOOGLE_BIGQUERY_ACCESS_TOKEN` +
  `GOOGLE_CLOUD_PROJECT` (the BigQuery sandbox requires no billing account).

Notes: already-wired keyed adapters (Shodan, OpenCorporates, and similar) keep
their recorded key states. HIBP direct email lookups stay out under nothing-paid.

## 2. Provider permissions

- [ ] **OpenSky** — their terms require written permission for REST integration;
      needed for transport_movement live coverage.
- [ ] **EUIPO** — sandbox/production approval after the free developer account.

## 3. Owner confirmations (needed near the end)

- [ ] **P17.10 live cascade on the owner's own seed** — confirm/deny candidate
      identities (mine / not-mine). The live run (`39161463451`) produced 1
      identity cluster awaiting confirmation
      (`4bb198ed-daa5-4412-a1cc-dbd34872e7bb` — see
      `runs/e86fefe0-ff40-4c98-b7e8-9d846b59460b/cascade/next_actions.json`
      in artifact `aletheia-live-cascade-39161463451`). These are the first
      real calibration labels; the calibrator stays untrained until they exist.
- [ ] Optional: **verified-live promotion** of adapters exercised by authorized
      runs (evidence already copied; the promotion itself is a bookkeeping
      decision).
- [ ] Optional: **GHunt** against the owner's own Google account (operator's own
      account only; read-only; authenticated-workflow exception).

## 4. Redlines (provisional defaults in force — say the word to change any)

1. Adaptive depth: default 3, escalate to 5 on HARD evidence in owner mode.
2. Owner-mode pivots: email/name/phone on; subject mode off unless declared.
3. Case model: opt-in `--case X`.
4. Cache TTL: 30 days profiles / 7 days DNS.
5. Face search: corroboration-only.
6. Completeness wave order: keyless-first, A → E.
7. Dark web behind container-level Tor; live dark-web runs remain gated.

## 5. Optional: new live targets

Any live-run target beyond today's on-file authorization needs a fresh Gate 2
assertion written by the owner (ownership + authorization; public, legal, open
sources only). Currently on file: `username:frost2233` (owner self-audit).
