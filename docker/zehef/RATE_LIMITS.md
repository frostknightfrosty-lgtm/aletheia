# Zehef sub-source — source review (`docker/zehef`)

Upstream: <https://github.com/N0rz3/Zehef> (GPL-3.0-only). Version 2.2.1 per
`config.json`; the project publishes no releases or tags, so the checkout is
pinned by commit `5b0c120efe846eae944dfea9410f925ca3036103` (master). The
Dockerfile verifies `git rev-parse HEAD` against the pin at build time, wipes
`.git`, and writes the commit to `/opt/zehef/PINNED_COMMIT`; the driver
reports it in every output document.

## What the image runs

`docker/zehef/run_zehef.py` (this repository's driver) imports only the 17
account-registration modules from `modules/accounts/` and calls each once
with the target email, in the upstream order used by `lib/cli.py`:

`adobe`, `bandlab`, `chess`, `deezer`, `duolingo`, `flickr`, `github`,
`gravatar`, `imgur`, `instagram`, `picsart`, `pinterest`, `pornhub`,
`protonmail`, `spotify`, `strava`, `twitter` (module attribute `x`).

### Deliberately not invoked

| Upstream part | Why not |
| --- | --- |
| `modules/breaches/pastedumper.py` (paste search) | Builds a `site:pastebin.com "<email>"` query and parses Google's result page (`google.com/search`). No documented API, brittle HTML scraping, and search pages are subject to controls this project does not bypass; paste-index coverage is tracked separately. |
| `modules/breaches/hudsonrock.py` (Cavalier API) | Queries `cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email` with a hardcoded shared api-key and returns stealer-log fields including credential material (top passwords/logins). Credential fields are excluded structurally; Hudson Rock is tracked as its own candidate (`VERIFICATION.md` §B 7). |
| `lib/emails_gen.py` (`Email_Gen`) | Generates random email combinations; not investigative output. |
| `lib/update.py` (`Version_Checker`) | Fetches the upstream master `config.json` on every CLI start (a self-update check); the driver never runs it. |

The driver imports `modules.accounts`, which also imports the outer
`modules` package (including the breach modules, which perform no I/O at
import time). Nothing from the table above is ever called.

## Endpoint inventory (as implemented by the pinned commit)

| Module | Request(s) | Positive ("registered") signal |
| --- | --- | --- |
| adobe | `POST https://auth.services.adobe.com/signin/v2/users/accounts` | non-empty `authenticationMethods`; JSON body `{username, usernameType: EMAIL}`, public sign-in client header `x-ims-clientid: homepage_milo` |
| bandlab | `GET https://www.bandlab.com/api/v1.3/validation/user?email=` | `valid` and not `available` |
| chess | `POST https://www.chess.com/callback/email/available?email=` | `isEmailAvailable` false |
| deezer | `POST https://www.deezer.com/ajax/gw-light.php` (`deezer.getUserData` then `deezer.emailCheck`) | `availability` false; anonymous API token only |
| duolingo | `GET https://www.duolingo.com/2017-06-30/users?email=` | non-empty `users` array |
| flickr | `GET https://www.flickr.com/` (API key extracted from the public page, upstream behavior) then `GET https://api.flickr.com/services/rest` (`flickr.people.search`) | non-empty `people`; prints the `Account` profile URL |
| github | `GET https://api.github.com/search/users?q=<email>+in:email` then `GET https://api.github.com/users/<login>` | non-zero `total_count`; prints Username, Name, Id, Avatar, Created on, Update on, Account URL (unauthenticated rate limit applies) |
| gravatar | `GET https://en.gravatar.com/<sha256(email)>.json` | profile JSON; prints display name and profile URL |
| imgur | `POST https://imgur.com/signin/ajax_email_available` | `available` false |
| instagram | `GET https://www.instagram.com/accounts/emailsignup/` (csrf cookie) then `POST https://www.instagram.com/api/v1/web/accounts/web_create_ajax/attempt/` | error code `email_is_taken`; the POST is an availability probe (empty fields, no password and no confirmation step is completed, so no registration completes) |
| picsart | `GET https://api.picsart.com/users/email/existence?email_encoded=1&emails=` | truthy response |
| pinterest | `GET https://www.pinterest.fr/resource/EmailExistsResource/get/` | non-empty `resource_response.data` |
| pornhub | `GET https://fr.pornhub.com/signup` (token) then `POST https://fr.pornhub.com/user/create_account_check` | `create_account_failed` (e-mail taken); probe only, no registration completes |
| protonmail | `POST https://account.proton.me/api/auth/v4/sessions` then `POST /api/core/v4/auth/cookies` (anonymous session, no user credentials) then `GET /api/core/v4/users/available?Name=&ParseDomain=1` | neither empty `Suggestions` nor `Code` 1000; only for protonmail-family domains; a `Created on` detail is derived from `GET https://api.protonmail.ch/pks/lookup?op=index&search=` when the key endpoint has a creation record |
| spotify | `GET https://spclient.wg.spotify.com/signup/public/v1/account?validate=1&email=` | `status` 20 |
| strava | `GET https://www.strava.com/frontend/athletes/email_unique?email=` | body `false` |
| twitter | `GET https://api.twitter.com/i/users/email_available.json?email=` | `taken` true |

## Bounds and behavior

- One request per service per run, sequential; no retries, no pagination, no
  account creation.
- Async modules get a 40s per-module timeout; the run is bounded by a 240s
  hard deadline after which partial results are printed with
  `deadline_exceeded: true` and the process exits 3 (the three synchronous
  modules — deezer, imgur, pornhub — call requests/httpx without a per-call
  timeout, so the deadline, not cancellation, is what bounds them).
- Output is one JSON document on stdout: `{sub_source, email, pinned_commit,
  modules: [{service, status, details, output[, error]}]}`. Per-module
  captured output is kept for the audit trail. Classification uses marker
  substitution in `lib.colors` before import instead of ANSI parsing; the
  detail keys parsed are Username, Name, Id, Avatar, Created on, Update on,
  and Account.
- The image installs only the three third-party runtime dependencies with
  pinned versions (httpx, requests, beautifulsoup4); `requirements.txt` also
  names `argparse` and `asyncio`, which are standard-library modules and are
  not installed from PyPI.
- Egress: httpx and requests honour `HTTP_PROXY`/`HTTPS_PROXY` from the
  environment by default, so live runs route through the egress proxy like
  every other network adapter.

## Legal position

Account-existence probes against public signup/availability endpoints. No
login is completed, no password reset is completed, no CAPTCHA or anti-bot
challenge is bypassed, and no account is created by these probes. Only run
against an email address with an explicit authorization assertion
(Gate 2). Tier 2 in `PROJECT_MANIFEST.json`; the Tier 5 floor is unchanged.
