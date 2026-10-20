# PicImageSearch sub-source — source review (`docker/picimagesearch`)

Upstream: <https://github.com/kitUIN/PicImageSearch> (MIT). The project's last
release tag is `v3.9.7` (2023-12-12); the current network layer (`httpx2`
migration), the current engine set, and the model layer all post-date it, so
the checkout is pinned by commit
`784713e546273a09aae4b247a8b6f798825efafa` (main, 2026-10-10, "chore(deps):
update all non-major dependencies (#390)"). The checkout self-reports version
`3.12.11` (`PicImageSearch/__init__.py`). The Dockerfile verifies
`git rev-parse HEAD` against the pin at build time, wipes `.git`, and writes
the commit to `/opt/picimagesearch/PINNED_COMMIT`; the driver reports it in
every output document.

## What the image runs

`docker/picimagesearch/run_picimagesearch.py` (this repository's driver)
imports five keyless engines from the pinned package and issues exactly one
request per engine per invocation, plus the official SauceNAO JSON API when
`SAUCENAO_API_KEY` is configured (reported as a recorded `skipped` otherwise).
The driver never imports the scrapers listed under "Deliberately not
invoked", the demo programs, or the token-update tooling.

| Driver key | Upstream class | Requests | Endpoint(s) |
| --- | --- | --- | --- |
| `iqdb` | `Iqdb(is_3d=False)` | 1 | `POST https://iqdb.org/` (multipart `file=` upload, or `url=` form field; the HTML result page is parsed by `IqdbResponse`) |
| `iqdb3d` | `Iqdb(is_3d=True)` | 1 | `POST https://3d.iqdb.org/` (real-life images) |
| `ascii2d` | `Ascii2D` | 1 | `POST https://ascii2d.net/search/file` or `/search/uri` — colour search only; the feature (`bovw`) search, which would issue a second GET, is never enabled |
| `tracemoe` | `TraceMoe` | 1 | `POST https://api.trace.moe/search?anilistInfo=&cutBorders=true` (anonymous tier; no `x-trace-key` is ever sent) |
| `animetrace` | `AnimeTrace` | 1 | `POST https://api.animetrace.com/v1/search` (multipart upload, or a `{"url": ...}` JSON body) |
| `sauce_nao` | `SauceNAO(api_key=...)` | 0–1 | `POST https://saucenao.com/search.php?testmode=0&numres=5&output_type=2&hide=0&db=999&minsim=30` — runs only when `SAUCENAO_API_KEY` is set; the pinned code documents the free-account limits (150 searches/day, 4 per 30 seconds) |

Maximum HTTP requests per invocation: 6. No pagination, no retries, no
caching; each engine is constructed fresh per run and no cookies persist
beyond it.

`--selftest` re-derives the reviewed inventory (5 keyless engines + the
conditional SauceNAO binding), refuses to pass if any engine's effective
client user agent is not the honest agent, if any engine reports TLS
verification off, or if the normalization stubs do not round-trip; `--health`
and the run path fail closed on the same UA/TLS checks.

## Documented deviations from pinned behaviour (both fail closed)

1. **The hardcoded browser user agent is replaced with a fixed honest
   agent.** `network.DEFAULT_HEADERS` ships a Chrome 139 user agent; the
   driver constructs every engine with `headers={"User-Agent": "Aletheia/0.9.0
   (picimagesearch)"}`, which wins the case-insensitive merge in
   `network._merge_headers` (last spelling and value are kept). The run path
   and the selftest read the effective header off each engine's client and
   refuse to run if the honest agent is not in effect.
2. **TLS verification is never disabled.** `network.py` builds the client
   with `create_ssl_context(verify=True)` and `follow_redirects=True`; the
   driver never passes `verify_ssl` (or any proxy) and refuses to run if any
   engine reports verification off.

Both facts are recorded in every run document (`user_agent`,
`tls_verified`).

## Deliberately not invoked

| Upstream part | Why not |
| --- | --- |
| `Google`, `GoogleLens`, `Yandex`, `Bing`, `BaiDu` | Consumer-web result-page scrapes with anti-bot handling; the per-engine terms review does not clear scraping of these services, and the self-hosted `search-engines` adapter already carries authorized general search. |
| `Copyseeker` | Relies on frozen server-action tokens that the upstream repository continuously regenerates through the scheduled `update_copyseeker_tokens` workflow; refreshing tokens against a protected endpoint implies bypassing site access controls. |
| `Lenso` | Upstream documents the engine as deprecated after Cloudflare Turnstile protection was added; the client cannot work without evading that control. |
| `Tineye` | Commercial service; the engine scrapes the web application's internal result endpoints and no free API tier exists. |
| `EHentai` | Adult gallery site (the exhentai path additionally needs login cookies); not needed for image provenance work, so no path is shipped. |
| `demo/` programs, `docs/`, `.github/scripts/` tooling | Demonstration and maintenance code; never imported by the driver. |

## Transport and egress

- The pinned network layer builds `httpx2.AsyncClient(proxy=proxies, ...)`
  with `proxies=None` from this driver, so httpx's default `trust_env=True`
  applies and live runs route through the container's `HTTP_PROXY` /
  `HTTPS_PROXY` (the audited egress proxy) — the same environment wiring the
  CI egress scenario injects. This is to be confirmed at the first authorized
  live run (no live run has occurred yet).
- Redirects are followed (`follow_redirects=True` in the pinned layer; engine
  result pages rely on it); the driver adds no redirect policy of its own.
- The only host contacted is the engine's own API host. The submitted image
  is either fetched by the engine from the supplied https URL, or uploaded
  to the engine directly; nothing is downloaded by this driver.
- Explicit authorization is required for every target image
  (`requires_authorization_assertion=True`): the image (or its URL) is
  transmitted to up to five third-party engines, so the operator must be
  authorized to share it.

## Output and failure semantics

- The driver prints one JSON document: `source`, `sub_source`,
  `pinned_commit`, `checkout_version`, `user_agent`, `tls_verified`,
  `target`, `target_kind`, `requested_engines`, `reported_engines`, `status`,
  and `engines` (per-engine `status`, `error`, `result_url`, `count`,
  `items[]`; `frame_count`/`api_error` for tracemoe; `code`/`ai`/`trace_id`
  for animetrace; quota fields for sauce_nao).
- Per-engine statuses: `ok` (items returned), `empty` (clean response, no
  items), `blocked` (HTTP 401/403/429 or a block marker in the error text),
  `error`, `skipped` (sauce_nao without a key).
- Run status: `ok` when any engine returned items; else `empty` when any
  engine answered cleanly; else `blocked` when every non-skipped engine was
  blocked; else `error`. Blocked pages are recorded, never retried,
  challenged, or evaded.
- Exit codes: `0` ok/empty/blocked, `1` error, `2` usage/invalid target
  (non-https URL, missing or >12 MB file), `3` hard deadline (210 s
  watchdog; 150 s gather timeout).
- No endpoint is invented and no result is retried or cached across runs.
