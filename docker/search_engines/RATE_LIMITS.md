# Rate Limits, Authentication and Pins for the search_engines Batch Adapter Sub-Sources

Every endpoint, query-parameter name, authentication requirement, documentation URL and crawl id below was read from the sub-source's own official documentation. Where a source publishes no numeric limit this file says **not published** rather than inventing a number. No endpoint, parameter name or version here was inferred from an example response.

**Environment-variable names are this adapter's own configuration names, not vendor-published facts.** No vendor in this batch publishes an environment-variable name. The Marginalia API page documents the API key in the `API-Key` request header and documents a public development key; this adapter maps those to `MARGINALIA_API_KEY` and to the literal default `public`. The adapter chooses only the variable name; it invents no vendor fact.

## Sub-source summary

| Sub-source | Endpoint (verbatim from the vendor docs) | Auth (env var) | Documented limit | Format | Official docs URL |
|---|---|---|---|---|---|
| marginalia | `GET https://api2.marginalia-search.com/search?query=<query>` | API key in the **`API-Key`** request header on every request (`MARGINALIA_API_KEY`; when unset the documented public key `public` is used) | **not published** - the API page only says of the public key: "Note that this key cannot create custom filters, and often hits a rate limit." | JSON | https://about.marginalia-search.com/article/api/ |
| common-crawl-index | `GET https://index.commoncrawl.org/<CC-MAIN-YYYY-NN>-index?url=<url>&output=json` | None | **not published** | JSON / JSONL (one JSON object per line) | https://commoncrawl.org/get-started |

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

## Dropped candidates

| Candidate | Reason it was dropped | Source URL |
|---|---|---|
| searxng | SearXNG is a self-hosted metasearch engine, not a public API. Its JSON output is an instance-side configuration (the `search.formats` setting documented at https://docs.searxng.org/dev/search_api.html) that public instances typically disable, and the brief forbids the runner from operating a self-hosted instance. No public instance with verifiable structured output is used. | https://docs.searxng.org/dev/search_api.html |
| google-custom-search | Google's own documentation states verbatim "The Custom Search JSON API is closed to new customers" and "This API is not available for new customers", with the service discontinuation on January 1, 2027. A new deployment cannot register. | https://developers.google.com/custom-search/v1/overview |

Both dropped candidates are still reported once per run by `docker/search_engines/runner.py` as skipped sources carrying the exact reason above, so each omission is auditable and no endpoint is invented for it.

## Overlap with existing adapters

**None.** The batch owner checked `PROJECT_MANIFEST.json` and found no existing adapter covering either sub-source: no manifest entry covers the Marginalia Search API or the Common Crawl CDXJ/URL index, and neither candidate is implemented inside another adapter. (`code_search` covers Debian Code Search, `academic_search` covers scholarly records, and `ip_intelligence` covers IP address intelligence; none of them queries a general web search engine or the Common Crawl index.) Both sub-sources here are therefore implemented in `docker/search_engines/runner.py` and none is deferred to a sibling adapter.

## Version pins

Neither sub-source is a locally installed tool, so there is no artefact to pin. The image is `python:3.13-slim-bookworm` and the only versioned values used are the Common Crawl crawl id (`CC-MAIN-2026-39`, recorded above) and the Marginalia API page revision (updated 2025-12-08). No version was invented. This adapter's own descriptor is pinned at `version_pin="1.0"`.

## Notes

- **--health never touches the network.** `docker run --rm --network none <image> --health` prints exactly `ok` on stdout and an inventory JSON line on stderr listing each sub-source, its kind (`http_api` or `dropped`), its endpoint and a boolean saying whether its key environment variable is configured, with `"network_used": false`. It opens no socket and reads no secret value into the output (only a boolean).
- **Secrets are never printed or recorded.** The Marginalia API key is sent only in the `API-Key` request header, never in the request URL, so the recorded `endpoint` never contains a credential.
- **One request per sub-source per run.** The runner issues at most one HTTP request per implemented sub-source (two requests total) and never paginates. Result lists are truncated to 25 records with the untruncated count recorded in `record_count`.
- **A hit is not a conclusion.** A web-search hit or a web-index record is a source observation, not an authoritative record: a result can be stale, biased, spam or misattributed, and must be reviewed against the published page before it is relied on.
