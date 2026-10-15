# Rate Limits, Authentication and Pins for the code_search Batch Adapter Sub-Sources

Every endpoint, query-parameter name, authentication requirement and documented limit below was read from the sub-source's own official documentation or specification. Where a source publishes no numeric limit this file says **not published** rather than inventing a number. No endpoint, parameter name or version here was inferred from an example response.

**Environment-variable names are this adapter's own configuration names, not vendor-published facts.** No vendor in this batch publishes an environment-variable name. Each name below is mapped to the exact credential the vendor's own documentation requires (an API key in the `x-dcs-apikey` HTTP header). The adapter chooses only the variable name; it invents no vendor fact.

## Sub-source summary

| Sub-source | Input | Endpoint (verbatim from the project's own OpenAPI specification) | Auth (env var) | Documented limit | Format | Official docs URL |
|---|---|---|---|---|---|---|
| debian-code-search | keyword / package / code snippet | `GET https://codesearch.debian.net/api/v1/search` with query parameters `query` (required) and `match_mode` (optional) | API key in the HTTP header `x-dcs-apikey` (`DEBIAN_CODE_SEARCH_API_KEY`); the specification's security scheme is `{"api_key": {"type": "apiKey", "name": "x-dcs-apikey", "in": "header"}}` | **not published** - the OpenAPI specification states no numeric limit and the API-key FAQ only explains that keys exist so the service can throttle individual callers. | JSON | https://codesearch.debian.net/ and the OpenAPI specification https://codesearch.debian.net/openapi.json (title "Debian Code Search", version 1.4.0) |

The specification's server is `https://codesearch.debian.net/api/v1`. The implementation uses `GET /search`; the specification also documents `GET /searchperpackage` with the same parameters, which this adapter does not call.

## API key acquisition (from the project's own FAQ)

Per https://codesearch.debian.net/apikeys/faq you log in via salsa.debian.org and download your personal API key; non-personal keys are requested by emailing stapelberg@debian.org. A keyless request is answered HTTP 403, which is consistent with the documented key requirement.

## Phase A probe result (verbatim)

The parent recorded a live probe from this host: `GET https://codesearch.debian.net/api/v1/search` returned **HTTP 403** without a key, consistent with the documented key requirement. No keyed request was made.

## Dropped candidates

Each dropped candidate is reported once per run as a skipped source carrying the exact reason below, and is never queried. No endpoint, parameter or version is invented for it.

### gitlab-search

**Reason (verbatim):** GitLab's own Search API docs state verbatim "Every call to this API requires authentication." (https://docs.gitlab.com/api/search/), and a live probe of `GET https://gitlab.com/api/v4/search?scope=blobs&search=test` returned HTTP 401. The code-search scope therefore cannot be used without a token, and no token flow is implemented.

**Source URL:** https://docs.gitlab.com/api/search/

### publicwww

**Reason (verbatim):** PublicWWW's own API authentication docs state verbatim "A paid plan is required: without one, every endpoint except / and /v1/account answers 403 plan_required." (https://publicwww.com/docs/api/authentication/). A paid-only source is barred by standing rule 4, so it is not implemented. (Its documented base URL is https://api.publicwww.com with an Authorization: Bearer header, recorded for context only.)

**Source URL:** https://publicwww.com/docs/api/authentication/

## Overlap with existing adapters

**None.** The batch owner checked `PROJECT_MANIFEST.json` and found no existing Docker-invoked adapter covering Debian Code Search (or either dropped candidate), so `debian-code-search` is implemented in `docker/code_search/runner.py` and nothing is deferred to a sibling adapter.

## Version pins

Debian Code Search is not a locally installed tool, so there is no artefact to pin. The image is `python:3.13-slim-bookworm` and the versioned API surface is the Debian Code Search API v1 (OpenAPI specification version 1.4.0). No version was invented. This adapter's own descriptor is pinned at `version_pin="1.0"`.

## Notes

- **--health never touches the network.** `docker run --rm --network none <image> --health` prints exactly `ok` on stdout and an inventory JSON line on stderr listing each sub-source, its kind (`http_api` or `dropped`), its endpoint and whether its credential environment variable is configured, with `"network_used": false`. It opens no socket and reads no secret value into the output (only a boolean).
- **Secrets are never printed or recorded.** The Debian Code Search API key is sent only in the `x-dcs-apikey` request header; it never appears in the URL, the recorded endpoint or the runner output.
- **One request per run.** The runner issues at most one HTTP request (the single implemented sub-source) and never paginates.
- **No invented response fields.** The verified contract recorded in the batching plan did not include the OpenAPI response schema, so the runner records the parsed JSON document verbatim rather than assuming field names, and the adapter normalizes one record per sub-source from it.
