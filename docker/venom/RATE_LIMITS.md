# VENOM sub-source — source review (`docker/venom`)

Upstream: <https://github.com/ghostport-sudo/VENOM> (MIT, Copyright (c) 2026
Ghostport). Version 7.0 in the checkout; the project publishes no releases or
tags, so the checkout is pinned by commit
`6fa3a483abc9cb0a1d96567e33b2919be59522c6` (main, 2026-06-28, "feat:
Implement autonomous DuckDuckGo AI Agent and 100% accurate social
enumeration"). The Dockerfile verifies `git rev-parse HEAD` against the pin at
build time, wipes `.git`, and writes the commit to `/opt/venom/PINNED_COMMIT`;
the driver reports it in every output document.

## What the image runs

`docker/venom/run_venom.py` (this repository's driver) imports 29 module
classes from the pinned checkout's `modules` package and invokes each one
once (`module.run(session)`, the upstream fetch+normalize wrapper). The driver
never imports `venom.py` (the upstream CLI), `modules.search`, `modules.ai`,
`modules.web`, `modules.webui`, `modules.dorks`, `modules.export`,
`modules.render`, `modules.phone`, or the keyed classes of
`modules.breach`/`modules.domain`/`modules.email`.

Reviewed module sets, per seed type (driver key → upstream class):

| Seed | Driver keys |
| --- | --- |
| email (5) | `emailrep`, `crtsh_email`, `psbdmp`, `otx_email`, `github_commits` |
| username (12) | `social`, `github_user`, `github_orgs`, `github_commit_emails`, `gitlab`, `npm`, `pypi`, `keybase`, `twitter`, `telegram`, `steam`, `psbdmp_u` |
| domain (13) | `dns`, `whois`, `ip`, `wayback`, `crt_subs`, `urlscan`, `otx_domain`, `ht_dns`, `ht_rev`, `pulsedive`, `proxycheck`, `internetdb`, `otx_ip` |

That is 30 driver bindings over 29 distinct classes (`psbdmp` runs for both
email and username seeds). No key, account, or registration is ever needed:
every module is constructed with `api_key=None`, and the keyed classes are
not imported at all.

`--selftest` re-derives the inventory and refuses to run if the binding
count, the distinct-class count, or the reviewed key sets differ from this
review; `--health` and the run path fail closed on the same check, and the
run path additionally fails closed if the user-agent patch below cannot be
applied.

## Request inventory (at most one run per module per invocation)

| Driver key | Upstream class | Requests per run | Endpoint(s) |
| --- | --- | --- | --- |
| `emailrep` | `EmailRepModule` | 1 | `GET https://emailrep.io/<email>` (EmailRep public tier; HTTP 429 is recorded as `_rate_limited`, no retry) |
| `crtsh_email` | `CrtshEmailModule` | 1 | `GET https://crt.sh/?q=<email>&output=json` (first 60 certificate rows normalized) |
| `psbdmp` / `psbdmp_u` | `PSBDMPModule` | 1 | `GET https://psbdmp.ws/api/v3/search/<target>` (top 10 paste IDs; paste bodies are never fetched) |
| `otx_email` | `OTXEmailModule` | 1 | `GET https://otx.alienvault.com/api/v1/search/pulses/?q=<email>&limit=5` |
| `github_commits` | `GitHubEmailCommitsModule` | 1 | `GET https://api.github.com/search/commits?q=<email>&per_page=5` (unauthenticated search API) |
| `social` | `SocialEnumerationModule` | 36 | One `GET` per platform in the pinned `config.SOCIAL_PLATFORMS` (36 entries: GitHub, GitLab, Reddit, Pastebin, HackerNews, DeviantArt, Flickr, Gravatar, Keybase, Steam, SoundCloud, Replit, Vimeo, Bitbucket, Codepen, Dribbble, LeetCode, PyPI, NPM, Lichess, Last.fm, Letterboxd, Mastodon, DockerHub, Sourceforge, Duolingo, Telegram, Medium, Behance, Mixcloud, Codeforces, Chess.com, Imgur, Trakt, AboutMe, Wattpad); 10 concurrent, 10 s each, `allow_redirects=False`, at most one trailing-slash retry per platform; detection is status code, API JSON, or pinned body markers only |
| `github_user` | `GitHubUserModule` | 3 | `GET /users/<u>`, `/users/<u>/repos?per_page=8&sort=updated`, `/users/<u>/gists?per_page=5` |
| `github_orgs` | `GitHubOrgsModule` | 1 | `GET /users/<u>/orgs` |
| `github_commit_emails` | `GitHubCommitEmailsModule` | ≤6 | `GET /repos/<u>/<repo>/commits?per_page=5` for at most the 6 repositories returned by `github_user`; author emails are kept only when they do not contain `noreply` |
| `gitlab` | `GitLabUserModule` | 1 | `GET https://gitlab.com/api/v4/users?username=<u>` (public users endpoint) |
| `npm` | `NPMUserModule` | 1 | `GET https://registry.npmjs.org/-/user/org.couchdb.user:<u>` |
| `pypi` | `PyPIUserModule` | 1 | `GET https://pypi.org/user/<u>/` (public profile page; only the count of `package-snippet` blocks is normalized) |
| `keybase` | `KeybaseModule` | 1 | `GET https://keybase.io/_/api/1.0/user/lookup.json?username=<u>` (public API; proofs are cryptographic cross-links) |
| `twitter` | `TwitterOembedModule` | 1 | `GET https://publish.twitter.com/oembed?url=...` (X's own embed endpoint; no X page scraping) |
| `telegram` | `TelegramResolveModule` | 1 | `GET https://t.me/<u>` (public preview page; handle + `og:title`) |
| `steam` | `SteamProfileModule` | 1 | `GET https://steamcommunity.com/id/<u>?xml=1` (public XML profile) |
| `dns` | `DNSModule` | 4 | `GET https://dns.google/resolve?name=<domain>&type=A|MX|NS|TXT` (DNS over HTTPS) |
| `whois` | `WHOISModule` | 1 | `GET https://rdap.org/domain/<domain>` (RDAP; only registrar name, registration/expiry dates, and nameservers are normalized — registrant/contact data is not extracted) |
| `ip` | `IPResolutionModule` | 1 + local resolution | Address resolution via the container resolver (`socket.gethostbyname`/`gethostbyaddr`), then `GET https://ipinfo.io/<ip>/json` |
| `wayback` | `WaybackModule` | 1 | `GET https://web.archive.org/cdx/search/cdx?url=<domain>&output=json&fl=timestamp,statuscode&limit=5&collapse=timestamp:6` |
| `crt_subs` | `CrtshDomainModule` | 1 | `GET https://crt.sh/?q=%.<domain>&output=json` (certificate-transparency subdomains, wildcards stripped, sorted) |
| `urlscan` | `URLScanModule` | 1 | `GET https://urlscan.io/api/v1/search/?q=domain:<domain>&size=10` — read-only search; the driver never submits a scan |
| `otx_domain` | `OTXDomainModule` | 1 | `GET https://otx.alienvault.com/api/v1/indicators/domain/<domain>/general` |
| `otx_ip` | `OTXIPModule` | 1 | `GET https://otx.alienvault.com/api/v1/indicators/IPv4/<ip>/general` (runs against the address resolved by `ip`) |
| `ht_dns` | `HackerTargetPassiveDNSModule` | 1 | `GET https://api.hackertarget.com/hostsearch/?q=<domain>` (keyless tier, published daily cap) |
| `ht_rev` | `HackerTargetReverseIPModule` | 1 | `GET https://api.hackertarget.com/reverseiplookup/?q=<ip>` (runs against the resolved address) |
| `pulsedive` | `PulsediveModule` | 1 | `GET https://pulsedive.com/api/info.php?indicator=<domain>&pretty=1` (public tier, no key) |
| `proxycheck` | `ProxyCheckModule` | 1 | `GET https://proxycheck.io/v2/<ip>?vpn=1&asn=1&risk=1` (keyless tier; runs against the resolved address) |
| `internetdb` | `ShodanInternetDBModule` | 1 | `GET https://internetdb.shodan.io/<ip>` (keyless; runs against the resolved address) |

Maximum HTTP requests per invocation: email ≤ 5, username ≤ 54
(36 sweep + 3 GitHub profile + 1 orgs + ≤ 6 commit scans + 8 single calls),
domain ≤ 16. No pagination, no recursion, no retry loops are added by the
driver; the only retry inherited from the pinned code is the single
trailing-slash retry inside the social sweep.

## Documented deviations from pinned behavior (both fail closed)

1. **User-agent rotation is replaced with a fixed honest agent.** The pinned
   code picks a random desktop-browser user agent per request
   (`base.get_random_user_agent`, consumed by `BaseOSINTModule._request` and
   imported directly by the `email`, `breach`, `domain`, and `username`
   modules). Per `docs/LEGAL_MODEL.md`, browser impersonation is out of
   bounds, so the driver replaces the helper with one that always returns
   `Aletheia/0.9.0 (venom)` on each of the five module objects (the binding
   is resolved per module, so every site must be patched), verifies the
   replacement, and refuses to run if any patch target is missing. Modules
   that hardcode their own `VenomOSINT/6.0` user agent (emailrep, OTX,
   Pulsedive, ProxyCheck) keep it: it self-identifies the tool and does not
   impersonate a browser. `modules/config.py` declares a `requests.Session`
   with a Chrome user agent, but no included module uses it, so no request
   is ever made with it.
2. **TLS verification is forced back on.** `BaseOSINTModule._request`
   hardcodes `ssl=False` (and the social sweep calls
   `session.get(..., ssl=False)` directly). The driver runs every module
   against its own `aiohttp.ClientSession` subclass whose `_request` forces
   `ssl=True`, so no included module can silently disable certificate
   verification; a host with a bad certificate produces an honest per-module
   error instead.

Both deviations are recorded in every run document
(`user_agent`, `tls_verified: true`).

## Deliberately not invoked

| Upstream part | Why not |
| --- | --- |
| `HIBPBreachesModule`, `HIBPPastesModule`, `BreachDirectoryModule`, `LeakCheckModule`, `OSINTLeakModule`, `IntelXModule`, `PhonebookModule` | Keyed services (operator API keys); this adapter holds no keys and does not register accounts. `PhonebookModule` additionally carries a third-party shared key as a literal (`x-key`) in the pinned source — borrowed credentials are out of bounds. |
| `LeakLookupModule` | Falls back to `LEAK_LOOKUP_PUBLIC_KEY`, a third party's API key published in the upstream `config.py`; borrowed credentials are out of bounds. |
| `DehashedModule` | Scrapes the HTML of a paid, account-only search page; paywall-adjacent scraping, and no API exists without credentials. |
| `HoleheModule`, `GoogleProbeModule` | Account-registration/auth-flow probes. `HOLEHE_SITES` includes a Dropbox check that POSTs a login form with a placeholder password (`login_password: "x"`) — authentication attempts are out of bounds regardless of the password's validity. The Google probe duplicates the probe class already covered by the existing `holehe` adapter. |
| `PasswordKAnonymityModule` | Requires password material as input (HIBP k-anonymity range API); no password is ever handled by this project. |
| `SSLCertModule` | Opens a raw TCP socket to the target's port 443 with `CERT_NONE` and bypasses the audited HTTP egress path; the `ssl-tls` adapter already observes certificates through the proxy. |
| `MXBlacklistModule` | Resolves `<domain>.<rbl>` with `socket.getaddrinfo` against RBLs that list IP addresses, not domains — the query cannot produce a meaningful result. |
| `IPGeoModule` | Plain-HTTP `ip-api.com` endpoint (cleartext), and `ip` (`IPResolutionModule`) already reports ipinfo.io geolocation in the same run. |
| `BGPViewModule` | `api.bgpview.io` did not answer a review-time probe (transport error); no endpoint is shipped that did not respond. |
| `HunterDomainModule` | Requires a Hunter.io API key; not invoked (and not on the owner's free-key list). |
| `PhoneCarrierModule` (`modules/phone.py`) | Requires a NumLookupAPI key, so the adapter does not declare the `phone` input type. |
| `EmailSecurityPostureModule`, `EmailTxtClassifyModule` | Duplicate the existing `email-auth` adapter's SPF/DMARC/DKIM/TXT coverage; the four extra DoH queries per run add no new data class. |
| `GravatarModule` | The existing `gravatar` adapter enforces a documented output allowlist (no contact details, wallets, links, galleries, verified-account data). VENOM's module returns the profile payload unbounded, so it is not run; one query per run means the curated adapter remains the single path. |
| `RdapAdminEmailModule` | Extracts registrant/administrative contact emails from RDAP. The existing `rdap` adapter documents that privacy-proxy/contact data is excluded; this project keeps that decision. |
| `DuckDuckGoModule` (`modules/search.py`) | Scrapes DuckDuckGo HTML search pages; search-engine page scraping is out of bounds, and the `search-engines` adapter already covers authorized search APIs. |
| `modules/dorks.py`, `modules/web.py` dark-web link lists | Generate pre-built query URLs (no data gathering) — nothing is queried. |
| `modules/ai.py`, `modules/web.py`, `webui/`, `modules/export.py`, `modules/render.py`, `venom.py` | The AI analyst (needs LLM provider keys), the local web dashboard/server, the CLI, and the report renderers are never imported; the driver's only upstream imports are `modules.{base,breach,domain,email,username,config}`. |
| `--proxy-list` proxy rotation (CLI option) | Not used; no proxies are supplied by the driver and no rotation exists in the module code. |

## Transport and egress

- The driver passes no proxy argument to any module (`self.proxy` stays
  `None`), so `aiohttp`'s default `trust_env=True` behavior applies and live
  runs route through the container's `HTTP_PROXY`/`HTTPS_PROXY` (the audited
  egress proxy), exactly like the other aiohttp-based adapters.
- One local lookup is inherent to the domain path: `IPResolutionModule`
  resolves the seed domain with the container resolver. Every HTTP client in
  the project resolves its API hostnames the same way; no raw TCP connection
  is ever opened to the seed target itself.
- No retries beyond the pinned code's own single trailing-slash retry, no
  redirect following (`allow_redirects=False`), and no cookies or sessions
  outlive a single run.

## Output and failure semantics

- The driver prints one JSON document: `source`, `sub_source`, `target_type`,
  `target`, `pinned_commit`, `checkout_version`, `user_agent`,
  `tls_verified`, `status` (`ok` / `blocked` / `error` / `invalid_target`),
  `reported_modules`, and `modules` (each upstream `run()` result verbatim).
- A module whose upstream wrapper reports a WAF/Cloudflare block
  (`{"Status": "Protected/WAF"}`) makes the run status `blocked`; the adapter
  records explicit markers so an empty report is never indistinguishable
  from a real search.
- Exit codes: `0` ok/blocked, `1` error, `2` usage/invalid target, `3` hard
  deadline (200 s watchdog; 150 s gather timeout).
- Dead upstreams are reported, not fought: every failed module yields an
  error-shaped result that the adapter surfaces; no endpoint is invented and
  no result is retried or cached across runs.
