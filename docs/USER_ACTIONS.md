# User Actions — the only items reserved for the owner

> **Everything else is handled autonomously.** The campaign (`docs/CAMPAIGN_LOG.md`)
> builds, wires, and CI-verifies every free, open path on its own. This file lists —
> and nothing else — the items that genuinely require the owner. It is kept current;
> when the campaign stops, this file is the complete remainder.
>
> All items are free. Nothing here requires payment, and nothing paid will ever be
> adopted. Keyed sources are already built with recorded skip paths, so most of
> these convert a recorded skip into live coverage the moment the key exists.

## 1. Free API keys (Gate 3) — register, then store as GitHub Secrets

How: repo → **Settings → Secrets and variables → Actions → New repository secret**
(`frostknightfrosty-lgtm/aletheia`). The campaign records the exact env-var name and
the signup URL actually used during each scoped review (never guessed).

Known today (from the existing adapters):

- [ ] **LeakIX** — live `leak_checkers` path — secret `LEAKIX_API_KEY` — leakix.net
- [ ] **GrayhatWarfare** — live `leak_checkers` path — secret `GRAYHATWARFARE_TOKEN` — grayhatwarfare.com
- [ ] **Reddit** — `reddit-api` adapter — secrets `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` — register at reddit.com/prefs/apps
- [ ] **YouTube Data API** — `youtube-api` adapter + `youtube-geofind` — secret `YOUTUBE_API_KEY` — Google Cloud console

New sources from the completeness directive (signup URL + secret name recorded at
build review):

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
  requires them).
- **Transport (Gate 6):** OpenSky (registration **plus written integration
  permission**), BarentsWatch, Network Rail, National Rail, Deutsche Bahn.

Configuration values (no registration, still owner-provided):

- [ ] **Unpaywall** — the documented DOI endpoint requires a contact email —
  secret `UNPAYWALL_EMAIL` (see `PHASE17_RECHECKS.md` #33).
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
