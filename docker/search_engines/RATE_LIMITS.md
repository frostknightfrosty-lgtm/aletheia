# Rate Limits, Authentication and Pins for the search_engines Batch Adapter Sub-Sources

Every endpoint, query-parameter name, authentication requirement, documentation URL and crawl id below was read from the sub-source's own official documentation. Where a source publishes no numeric limit this file says **not published** rather than inventing a number. No endpoint, parameter name or version here was inferred from an example response.

**Environment-variable names are this adapter's own configuration names, not vendor-published facts.** No vendor in this batch publishes an environment-variable name. The Marginalia API page documents the API key in the `API-Key` request header and documents a public development key; this adapter maps those to `MARGINALIA_API_KEY` and to the literal default `public`. The adapter chooses only the variable name; it invents no vendor fact.

## Sub-source summary

| Sub-source | Endpoint (verbatim from the vendor docs) | Auth (env var) | Documented limit | Format | Official docs URL |
|---|---|---|---|---|---|
| marginalia | `GET https://api2.marginalia-search.com/search?query=<query>` | API key in the **`API-Key`** request header on every request (`MARGINALIA_API_KEY`; when unset the documented public key `public` is used) | **not published** - the API page only says of the public key: "Note that this key cannot create custom filters, and often hits a rate limit." | JSON | https://about.marginalia-search.com/article/api/ |
| common-crawl-index | `GET https://index.commoncrawl.org/<CC-MAIN-YYYY-NN>-index?url=<url>&output=json` | None | **not published** | JSON / JSONL (one JSON object per line) | https://commoncrawl.org/get-started |
| searxng (self-hosted) | `GET http://127.0.0.1:8888/search?q=<query>&format=json` (loopback-only instance operated inside this image; upstream pinned by commit below) | None | **not published** | JSON | https://docs.searxng.org/dev/search_api.html |

## Implemented sub-sources

### marginalia

- **Endpoint (verbatim):** `GET https://api2.marginalia-search.com/search?query=<query>`. The API page states: "The updated API is available through `api2.marginalia-search.com`." A documented test request is `curl -H "API-Key: ${API_KEY}" -XGET https://api2.marginalia-search.com/search?query=json+api`.
- **Authentication / header:** The API page states: "Pass the API key in the `API-Key` header on every request." The adapter sends `API-Key: <key>` on every request and never places the key in the URL.
- **Key configuration:** The environment variable is `MARGINALIA_API_KEY`. When it is unset the adapter uses the documented public key, quoted verbatim from the API page: "If you want to develop an integration but do not yet have a key, you can use the key `public`. Note that this key cannot create custom filters, and often hits a rate limit." The public key is therefore documented and rate-limited, and cannot create custom filters.
- **Free non-commercial key:** The API page documents a free non-commercial key obtained by emailing contact@marginalia-search.com ("Email contact@marginalia-search.com. The email step is necessary to prevent mass signup abuse.").
- **Documented rate limit: not published.** The page publishes no numeric rate or quota; it only says the public key "often hits a rate limit". No number is invented here.
- **Format:** JSON. The documented response is a JSON object carrying `query`, `license` and a `results` array whose entries have `url`, `title` and `description`.
- **Licence (non-commercial):** Content is "Provided under CC-BY-NC-SA 4.0" (https://creativecommons.org/licenses/by-nc-sa/4.0/). CC-BY-NC-SA is a **non-commercial** licence: results must not be used commercially and carry attribution and share-alike obligations. The runner records the returned `license` value in the payload and this adapter records the non-commercial restriction in its descriptor legal notes.
- **Official docs URL:** https://about.marginalia-search.com/article/api/ (page updated 2025-12-08).

### common-crawl-index

- **Endpoint (verbatim):** `GET https://index.commoncrawl.org/<CC-MAIN-YYYY-NN>-index?url=<url>&output=json`. The index server is `https://index.commoncrawl.org/`; the crawl id is a path segment and the adapter always uses an explicit pinned crawl, never a wildcard.
- **Authentication:** None. Common Crawl states verbatim: "Crawl data is free to access by anyone from anywhere." (https://commoncrawl.org/get-started)
- **Documented rate limit: not published.** The get-started page publishes no numeric rate or quota. The adapter records it as not published and issues at most one request per run.
- **Format:** JSON / JSONL - one JSON object per line. The documented CDX fields used are `urlkey`, `timestamp`, `url`, `mime`, `status`, `digest`, `length`, `offset` and `filename`.
- **Pinned crawl id:** `CC-MAIN-2026-39`. It is the most recent crawl id listed on the official crawl list at https://commoncrawl.org/get-started (the page lists it first, linking to https://data.commoncrawl.org/crawl-data/CC-MAIN-2026-39/index.html). The adapter exposes it as the module constant `COMMON_CRAWL_CRAWL_ID` with a comment naming that source URL, and records the same source in the payload as `crawl_id_source`.
- **Official docs URL:** https://commoncrawl.org/get-started.

### searxng (self-hosted, loopback only)

- **What it is:** SearXNG is a self-hosted metasearch engine, not a public API. The resolved route from the source-completeness review is to build it as a self-hosted container instance with the JSON endpoint enabled (free/open-source). The runner therefore installs the upstream project into this adapter's own image and operates it as a **loopback-only** instance for the duration of a run; no public instance is ever used.
- **Upstream pin (commit, never guessed):** `1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4` (2026-10-17). It is the release the project's own documentation builds from - the official documentation pages carry the version string `SearXNG Documentation (2026.10.17+1c10abe2d)` - and the commit's signature is verified in the upstream repository (https://github.com/searxng/searxng). The Dockerfile checks `git rev-parse HEAD` against this commit at build time.
- **Licence:** AGPL-3.0-or-later. The project is operated unmodified from the pinned commit; this repository ships configuration and a runner, not a modified distribution of SearXNG.
- **Installation (verbatim route):** the official source-install sequence at https://docs.searxng.org/admin/installation-searxng.html - system packages (`git`, build tools, `libxslt1-dev`, `zlib1g-dev`, `libffi-dev`, `libssl-dev`), the documented bootstrap packages (`pyyaml`, `msgspec`, `typing-extensions`, `pybind11`), then `pip install --use-pep517 --no-build-isolation -e .`.
- **Boot (verbatim route):** the same page's "Check" section: export `SEARXNG_SETTINGS_PATH` and run `python -m searx.webapp`. The generated instance settings bind `127.0.0.1:8888` (`server.bind_address` / `server.port`).
- **JSON output is an instance-side setting:** the search API page states: "Supported formats are defined in settings.yml, under the search: section." and "Requesting an unset format will return a 403 Forbidden error." The pinned default settings ship `search.formats: [html]`, so the runner's generated settings enable both `html` and `json` explicitly.
- **Engine set (documented `keep_only` mechanism):** the settings documentation (https://docs.searxng.org/admin/settings/settings.html) documents `use_default_settings: engines: keep_only: [...]`, which restricts the default engine list. The instance is kept to the keyless engines that are enabled by default in the pinned release - `duckduckgo`, `brave` and `wikipedia` - so each run fans out to exactly three engine requests (through the same egress proxy as every other sub-source in live runs).
- **Secret:** the pinned settings file documents the environment override verbatim: the `server.secret_key` value "Is overwritten by ${SEARXNG_SECRET}". The runner sets `SEARXNG_SECRET` to a random value at boot, so the settings file ships only a placeholder and no secret is ever printed or recorded.
- **Proxy routing:** the pinned settings file documents the proxy block verbatim (`outgoing.proxies.all://` taking a list of proxy URLs). When a proxy environment variable is present (live runs), the runner writes that proxy into the generated settings so the instance's engine requests are rate-limited and audited like all other outbound requests; loopback requests never use a proxy.
- **Documented rate limit: not published.** The search API page publishes no numeric rate or quota; it is recorded as not published rather than guessing a number. The runner issues exactly one loopback query per run; the instance makes one request per configured engine.
- **Offline self-test:** `--selftest-searxng` boots the instance on loopback with no external network, issues one query and prints a JSON report (the Docker integration capture case for this sub-source), so the boot + JSON contract is verified even where no engine is reachable.
- **Official docs URL:** https://docs.searxng.org/dev/search_api.html and https://docs.searxng.org/admin/installation-searxng.html.

## Dropped candidates

| Candidate | Reason it was dropped | Source URL |
|---|---|---|
| google-custom-search | Google's own documentation states verbatim "The Custom Search JSON API is closed to new customers" and "This API is not available for new customers", with the service discontinuation on January 1, 2027. A new deployment cannot register. | https://developers.google.com/custom-search/v1/overview |

The dropped candidate is still reported once per run by `docker/search_engines/runner.py` as a skipped source carrying the exact reason above, so the omission is auditable and no endpoint is invented for it.

## Overlap with existing adapters

**None.** The batch owner checked `PROJECT_MANIFEST.json` and found no existing adapter covering any of the sub-sources: no manifest entry covers the Marginalia Search API, the Common Crawl CDXJ/URL index or a SearXNG instance, and none is implemented inside another adapter. (`code_search` covers Debian Code Search, `academic_search` covers scholarly records, and `ip_intelligence` covers IP address intelligence; none of them queries a general web search engine, the Common Crawl index or a self-hosted metasearch instance.) All sub-sources here are therefore implemented in `docker/search_engines/runner.py` and none is deferred to a sibling adapter.

## Version pins

marginalia and common-crawl-index are remote APIs, so they have no artefact to pin; searxng **is** a locally installed tool and is pinned to the exact upstream commit `1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4` (verified at build time, recorded above). The image base is `python:3.13-slim-bookworm`; the other versioned values are the Common Crawl crawl id (`CC-MAIN-2026-39`, recorded above) and the Marginalia API page revision (updated 2025-12-08). No version was invented. This adapter's own descriptor is pinned at `version_pin="1.0"`.

## Notes

- **--health never touches the network.** `docker run --rm --network none <image> --health` prints exactly `ok` on stdout and an inventory JSON line on stderr listing each sub-source, its kind (`http_api`, `self_hosted_instance` or `dropped`), its endpoint and a boolean saying whether its key environment variable is configured, with `"network_used": false`. It opens no socket and reads no secret value into the output (only a boolean). It does **not** boot the embedded instance.
- **--selftest-searxng boots the instance offline.** The capture case runs `docker run --rm --network none <image> --selftest-searxng`: the embedded instance starts on loopback, one query is issued, and a JSON report is printed. No external network is used; engines are unreachable in this mode and are reported in the response's `unresponsive_engines` list.
- **Secrets are never printed or recorded.** The Marginalia API key is sent only in the `API-Key` request header, never in the request URL, so the recorded `endpoint` never contains a credential. The SearXNG instance secret exists only as a random in-process value passed via `SEARXNG_SECRET`.
- **One query per sub-source per run.** The runner issues at most one HTTP request per public-API sub-source (two requests total) plus one loopback query to the embedded SearXNG instance, which fans out to one request per configured engine (three engines) through the same egress proxy in live runs; it never paginates. Result lists are truncated to 25 records with the untruncated count recorded in `record_count`.
- **A hit is not a conclusion.** A web-search hit or a web-index record is a source observation, not an authoritative record: a result can be stale, biased, spam or misattributed, and must be reviewed against the published page before it is relied on.
