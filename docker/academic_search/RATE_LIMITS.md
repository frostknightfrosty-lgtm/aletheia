# Rate Limits for academic_search Batch Adapter Sub-Sources

Each sub-source's official documentation, exact search endpoint, verbatim search parameter, authentication requirement, documented rate/usage limit and response format. Every entry was read from the provider's **own** official documentation; where a provider publishes no numeric limit this file says **not published** rather than inventing a number. The raw probe recorded under each entry was run while this adapter was written.

| Sub-source | Base URL | Exact search endpoint (verbatim from docs) | Documented search parameter (verbatim) | Auth | Documented rate/usage limit | Response format | Official docs URL |
|---|---|---|---|---|---|---|---|
| openalex | https://api.openalex.org | `https://api.openalex.org/works?search=dna` | `search` — "The `search` parameter finds results matching a given text search." | None for basic use; optional free API key sent as the `api_key` query parameter or as `Authorization: Bearer YOUR_KEY` | "No API key: 10" requests per second; "Free API key, or prepaid usage: 30"; "Annual plan: 50"; "`per_page` maximum: 100"; "Basic paging limit: 10,000 results" | JSON | https://help.openalex.org/api/searching/ and https://help.openalex.org/api/authentication/ |
| crossref | https://api.crossref.org | `https://api.crossref.org/works?query.bibliographic=Richard+Feynmann` | `query.bibliographic` — "`/works?query.bibliographic=Richard+Feynmann` only incorporates fields used when referencing the content item (title, authors, volume, journal name, etc.)"; the generic `query` parameter is documented as "Query certain fields" | None; optional `mailto` — the reference documents it as "The email address to identify yourself and access the 'polite pool'" and does not require it for any request | not published | JSON | https://api.crossref.org/swagger-docs (Crossref REST API reference; also reachable from https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |
| semantic-scholar | https://api.semanticscholar.org | `https://api.semanticscholar.org/graph/v1/paper/search?query=covid+vaccination&offset=100&limit=3` | `query` — documented verbatim in the example requests of the official "Paper relevance search" operation; the published specification defines no separate parameter table for that operation | None for the public endpoints; optional free API key — "If you are using an API key, it must be set in the header `x-api-key` (case-sensitive)" | "rate-limited to 1000 requests per second shared among all unauthenticated users. Requests may also be further throttled during periods of heavy use." and "The introductory rate limit for an API key is 1 RPS on all endpoints." | JSON | https://api.semanticscholar.org/api-docs/graph (Redoc over https://api.semanticscholar.org/graph/v1/swagger.json) and https://www.semanticscholar.org/product/api |
| arxiv | http://export.arxiv.org | `http://export.arxiv.org/api/query?search_query=all:electron` | `search_query` — parameter table row "`search_query`" | None (unauthenticated) | "In cases where the API needs to be called multiple times in a row, we encourage you to play nice and incorporate a 3 second delay in your code."; `max_results` > 30,000 returns HTTP 400 | Atom XML | https://info.arxiv.org/help/api/user-manual.html |
| core | https://api.core.ac.uk | `GET /v3/search/{entityType}/` with `q` — the specification's own example is `https://api.core.ac.uk/v3/search/works/?q=abstract:"bibliometrics"` | `q` — "Search query (use specific fields like doi, title, authors, etc.)", `required=true` | None required — "Access to the CORE API is free and requires no authentication."; registered users may send the key as the query parameter `api_key` or as the header `Authorization: Bearer [API_KEY]` | "Unauthenticated users … 100 tokens per day, maximum 10 per minute."; "Registered Personal users … 1,000 tokens per day, maximum 25 per minute."; "Registered academic users NOT affiliated with Supporting or Sustaining institutions … 5,000 tokens per day, maximum 10 per minute."; the CORE services page also states "One batch request or five single requests per 10 seconds." | JSON | https://api.core.ac.uk/docs/v3 (specification: https://api.core.ac.uk/swagger/v3.json) and https://core.ac.uk/services/api |
| openaire | https://api.openaire.eu/graph | `GET /v3/research-products?search=...` | `search` — "Keyword-based search."; the same operation also documents `mainTitle` ("Search in the research product's main title") and `authorFullName` | None declared — the published specification contains no security scheme, so requests are unauthenticated | "The rate limit for the former type of requests is up to 7200 requests per hour, while the latter is up to 60 requests per hour." (authenticated / unauthenticated) | JSON | https://graph.openaire.eu/docs/apis/graph-api/ (specification: https://api.openaire.eu/graph/v3/api-docs) and https://graph.openaire.eu/docs/apis/terms |

---

**Dropped sub-source: unpaywall (not queried at all).**

- **Drop reason.** The Unpaywall REST API documents no title, keyword or author search. Its endpoint list contains exactly two entries: `GET /v2/:doi` ("Accepts: A valid DOI") and `GET /v2/search?query=:your_query`, which the documentation itself marks **"Retired 18 September 2026. This endpoint now returns `410 Gone`. Use OpenAlex search instead."** Because this adapter's input types are name-based (`name`, `company_name`, `person_name`) and the repository defines no DOI seed type, there is no documented request contract to call. The runner therefore reports unpaywall once per run as a skipped source with that exact reason and never builds a URL for it.
- **For the record (verified, but unusable here).** Endpoint `GET /v2/:doi`; documented example `https://api.unpaywall.org/v2/10.1038/nature12373?email=YOUR_EMAIL`; the documentation states "Requests must include your email as a parameter at the end of the URL, like this: `api.unpaywall.org/my/request?email=YOUR_EMAIL`." — the email parameter is **required for every request**, so a runner that did call it would have to record a skip reason whenever the email environment variable were unset. Rate limit: "Please limit use to 100,000 calls per day." Response format: JSON. Official docs: https://unpaywall.org/products/api. It is dropped only because it offers no search over the seed types this adapter accepts.

**Notes:**

- **No implemented sub-source requires a credential.** OpenAlex, Crossref, Semantic Scholar, arXiv, CORE and OpenAIRE all answer unauthenticated requests according to their own documentation, so no sub-source is skipped for a missing key. The optional keys (`OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `CORE_API_KEY`) and the optional polite-pool address (`CROSSREF_MAILTO`) are only sent when their environment variable is set, and no key is ever printed.
- **One request per sub-source per run.** The runner sends six requests per run and never paginates; that is well inside every documented per-second limit above. Implement backoff on 429/5xx responses.
- **Response formats.** Five JSON APIs and one Atom XML API (arXiv, parsed with the standard library `xml.etree.ElementTree`). No third-party package is used.
- **A hit is a scholarly-record match, not a confirmed identity match.** Free-text search returns records that mention the query text; author attribution must be reviewed by a human against the published record.

## Raw probes recorded while writing this adapter

All probes used harmless public queries (`test`) or a DOI, were sent unauthenticated, and were run on 2026-10-15 (host clock) from a Windows host with `Invoke-WebRequest`.

```
=== openalex :: https://api.openalex.org/works?search=test&per-page=2
HTTP 200 | content-type: application/json | bytes: 24091
BODY-HEAD: {"meta": {"count": 38729292, "db_response_time_ms": 969, "page": 1, "per_page": 2, "groups_count": null, "x_query": {"oql": "get works where full text has (test)", ...}}, "results": [...]

=== crossref :: https://api.crossref.org/works?query.bibliographic=test&rows=2
HTTP 200 | content-type: application/json | bytes: 4261
BODY-HEAD: {"status":"ok","message-type":"work-list","message-version":"1.0.0","message":{"facets":{},"total-results":763868,"items":[{"institution":[...],"DOI":"10...

=== semantic-scholar :: https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=2
HTTP 429 (three attempts, ~12 s and ~20 s apart) | body: {"message": "Too Many Requests. Please wait and try again or apply for a key for higher rate limits. https://www.semanticscholar.org/product/api#api-key-form", "code": "429"}
The endpoint responded and rejected the request with the documented shared-pool throttle; this is the behaviour the published limit describes ("1000 requests per second shared among all unauthenticated users. Requests may also be further throttled during periods of heavy use.").

=== arxiv :: http://export.arxiv.org/api/query?search_query=all:test&max_results=2
HTTP 200 | content-type: application/atom+xml; charset=utf-8 | bytes: 3247
BODY-HEAD: <?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" ... <entry><id>http://arxiv.org/abs/1101.4081v3</id> ...
(# the same host and path also answered HTTP 200 over https://export.arxiv.org/api/query)

=== core :: https://api.core.ac.uk/v3/search/works/?q=test&limit=2
HTTP 429 (two attempts, ~25 s apart) | empty body
The endpoint responded and rejected the unauthenticated request; CORE documents the unauthenticated budget as "100 tokens per day, maximum 10 per minute", which this shared host had exhausted.

=== openaire :: https://api.openaire.eu/graph/v3/research-products?search=test&pageSize=2
HTTP 200 | content-type: application/json | bytes: 6343
BODY-HEAD: {"header":{"numFound":7685270,"maxScore":3.877022,"queryTime":237,"page":1,"pageSize":2},"results":[{"authors":[{"id":null,"fullName":"Developer Account",...

=== unpaywall (dropped; probe recorded for the drop decision) :: https://api.unpaywall.org/v2/10.1038/nature12373?email=unpaywall_01@example.com
HTTP 200 | content-type: application/json | bytes: 5049
BODY-HEAD: {"best_oa_location":{...},"data_standard":2,"doi":"10.1038/nature12373",...
```
