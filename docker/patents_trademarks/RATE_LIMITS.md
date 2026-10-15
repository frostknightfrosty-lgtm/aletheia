# Rate Limits, Authentication and Pins for the patents_trademarks Batch Adapter Sub-Sources

Every endpoint, query-parameter name, authentication requirement and documented limit below was read from the sub-source's own official documentation or confirmed against the live sub-source endpoint. Where a source publishes no numeric limit that could be verified from a reachable official page this file says **not published** rather than inventing a number. No endpoint, parameter name or version here was inferred from an example response, and no candidate was kept alive by guessing a contract.

**Environment-variable names are this adapter's own configuration names, not vendor-published facts.** No vendor in this batch publishes an environment-variable name. Each name below is mapped to the exact credential the vendor's own documentation requires (the `X-API-KEY` header, the `USPTO-API-KEY` header, or OAuth 2.0 client credentials). The adapter chooses only the variable name; it invents no vendor fact.

## Sub-source summary (implemented)

| Sub-source | Base URL and exact endpoint (verbatim from the vendor's docs / confirmed live) | Search parameters | Auth (env var) | Documented limit | Format | Official docs URL |
|---|---|---|---|---|---|---|
| uspto-open-data | `GET https://api.uspto.gov/api/v1/patent/applications/search` | `q` (boolean AND/OR/NOT, `*` wildcard, quoted phrases), `dateRangeData.startDate`, `dateRangeData.endDate`, `start` (offset), `rows` (max 25) | Free USPTO Open Data Portal API key in the `X-API-KEY` header (`USPTO_ODP_API_KEY`) | **not published** — the ODP getting-started page states per-key limits are enforced and a request over the limit is answered with HTTP 429; no numeric request rate is retrievable from a reachable official page. | JSON | https://data.uspto.gov/apis |
| uspto-patent-assignment | `GET https://api.uspto.gov/api/v1/patent/applications/{applicationNumberText}/assignment` | Path parameter `applicationNumberText` (e.g. `14412875`). The route returns the assignment data object for that application; the ODP publishes no assignor/assignee search parameter. | Free USPTO Open Data Portal API key in the `X-API-KEY` header (`USPTO_ODP_API_KEY`, the same key as uspto-open-data) | **not published** — same ODP per-key limit, HTTP 429 when exceeded. | JSON | https://data.uspto.gov/apis |
| uspto-tsdr | `GET https://tsdrapi.uspto.gov/ts/cd/casestatus/sn{serial}/info.xml` | Path segment `sn<serial>` documents a trademark serial number (the official guide's sample is `sn78787878`). The same guide documents `info.xml` for case status and `last-update/info.json?sn=<serial>` for the last-update time. | Free USPTO TSDR API key in the `USPTO-API-KEY` header (`USPTO_TSDR_API_KEY`) | **60 requests per API key per minute** for status endpoints; **4 per minute** for PDF/ZIP downloads; off peak (10 p.m. to 5 a.m. EST) **120** and **12** per minute. Source: the USPTO TSDR API Key Manager user guide. | XML (`info.xml`); the API also serves PDF, ZIP and JSON representations | https://www.uspto.gov/sites/default/files/documents/tm-enterprise-api-user-guide-v2.pdf and https://developer.uspto.gov/api-catalog/tsdr-data-api |
| epo-ops | Token: `POST https://ops.epo.org/3.2/auth/accesstoken`; search: `GET https://ops.epo.org/3.2/rest-services/published-data/search?q={query}` | `q` (the OPS CQL search query; the caller may pass a publication number, an applicant or a keyword). The adapter sends the seed value as the `q` value and invents no field qualifier. | Free EPO OPS consumer key and secret (EPO developer account) exchanged for an OAuth 2.0 bearer token via HTTP Basic client credentials (`EPO_OPS_CONSUMER_KEY` / `EPO_OPS_CONSUMER_SECRET`) | **not published** — no requests-per-second number is retrievable from a reachable official page; the EPO fair-use policy governs and a keyless request is answered HTTP 403 "violation of Fair Use policy". The project's recovered verification note (not independently re-verified here) records a 4 GB/week free data quota. | XML (`Accept: application/xml`) | https://developers.epo.org/ (OPS v3.2 reference: https://link.epo.org/web/ops_v3.2_documentation_-_version_1.3.19_en.pdf) |

## uspto-open-data — USPTO Open Data Portal Patent Search API

- **Endpoint (verbatim):** `GET https://api.uspto.gov/api/v1/patent/applications/search`. The ODP also documents `POST /api/v1/patent/applications/search` with a JSON body and `GET /api/v1/patent/applications/{applicationNumberText}`; this adapter queries only the documented GET search route once per run.
- **Exact parameter names:** `q`, `dateRangeData.startDate`, `dateRangeData.endDate`, `start`, `rows`. The adapter sends `q`, `rows=25` and `start=0`.
- **Auth:** free ODP API key in the `X-API-KEY` request header, requested from the USPTO API Key Manager at https://account.uspto.gov/api-manager/. Env var: `USPTO_ODP_API_KEY`.
- **Documented limit:** not published as a reachable number. The ODP documentation states that per-key limits are enforced and a request over the limit is answered with HTTP 429.
- **Format:** JSON. The documented response object carries `count`, `patents` (an array) and `requestIdentifier`; each patent carries `applicationNumberText`, `inventionTitle`, `patentNumber`, `applicationFilingDate`, `grantDate`, `applicationStatusCode`, `applicationStatusDate`, `applicationTypeLabelName`, `inventors[].inventorNameText` and `applicants[].applicantNameText`.
- **Docs URL:** https://data.uspto.gov/apis (the ODP API documentation and getting-started pages; the machine-readable query reference is https://data.uspto.gov/documents/documents/ODP-API-Query-Spec.pdf and the OpenAPI source is https://data.uspto.gov/swagger/swagger.yaml).

## uspto-patent-assignment — USPTO Open Data Portal patent application assignment data

- **Endpoint (verbatim):** `GET https://api.uspto.gov/api/v1/patent/applications/{applicationNumberText}/assignment`.
- **Exact parameter names:** path parameter `applicationNumberText` (e.g. `14412875`). The adapter sends the seed value only when it is numeric; a value that also carries letters is reported as a documented skip instead of being truncated.
- **Auth:** free ODP API key in the `X-API-KEY` header (`USPTO_ODP_API_KEY`), the same key as uspto-open-data.
- **Documented limit:** not published as a reachable number (same ODP per-key limit, HTTP 429).
- **Format:** JSON (`type: object`; the ODP publishes no fixed property list for this route, so the runner stores the returned object verbatim under `assignment`).
- **Docs URL:** https://data.uspto.gov/apis.
- **Note on the plan's input types:** the recovered verification note records that assignment records migrated to the Open Data Portal at this application-number-keyed route. The ODP publishes no assignor/assignee search parameter, so the adapter implements the migrated route rather than inventing a search endpoint.

## uspto-tsdr — USPTO Trademark Status and Document Retrieval API

- **Endpoint (verbatim from the USPTO API Key Manager user guide, Appendix "Sample URL search queries"):** `GET https://tsdrapi.uspto.gov/ts/cd/casestatus/sn78787878/info.xml` (the adapter's template replaces `78787878` with the seed's serial number).
- **Exact parameter names:** the serial number is the path segment `sn<serial>`. No query parameter is documented for case status.
- **Auth:** free TSDR API key in the `USPTO-API-KEY` request header, requested from the USPTO API Key Manager at https://account.uspto.gov/api-manager/ ("you must enter USPTO-API-KEY exactly"). Env var: `USPTO_TSDR_API_KEY`.
- **Documented limit:** 60 requests per API key per minute for all status requests and 4 per minute for PDF/ZIP downloads; off peak (10 p.m. to 5 a.m. EST) 120 and 12 per minute. A request over the limit is answered with HTTP 429.
- **Format:** XML at `info.xml`; the same guide documents `content` (HTML), `download.pdf`, `content.zip`, `casedocs/bundle.*` and `last-update/info.json`.
- **Docs URL:** https://www.uspto.gov/sites/default/files/documents/tm-enterprise-api-user-guide-v2.pdf and https://developer.uspto.gov/api-catalog/tsdr-data-api.

## epo-ops — EPO Open Patent Services (OPS)

- **Endpoints (verbatim):** token `POST https://ops.epo.org/3.2/auth/accesstoken` with HTTP Basic credentials and `grant_type=client_credentials`; search `GET https://ops.epo.org/3.2/rest-services/published-data/search?q=<query>` with an `Authorization: Bearer <token>` header.
- **Exact parameter names:** `q` on the search route (OPS CQL). No field qualifier is added by the adapter; the seed value is sent unchanged.
- **Auth:** free EPO OPS developer account. A consumer key and secret are exchanged at the token endpoint for a bearer token. Env vars: `EPO_OPS_CONSUMER_KEY`, `EPO_OPS_CONSUMER_SECRET`.
- **Documented limit:** not published as a reachable requests-per-second number. The EPO fair-use policy governs and a keyless request is answered HTTP 403 `<message>This request has been rejected due to the violation of Fair Use policy</message>`. The project's recovered verification note records a 4 GB/week free data quota; that number was not independently re-verified here.
- **Format:** XML (the runner asks for `application/xml` and reads `document-id` elements plus the `total-result-count` attribute).
- **Docs URL:** https://developers.epo.org/ (OPS page: https://www.epo.org/en/searching-for-patents/data/web-services/ops; OPS v3.2 reference and swagger PDFs are linked from the developer portal).

## Dropped candidates

| Candidate | Exact reason it was dropped | Evidence |
|---|---|---|
| patentsview | The documented PatentsView Search API host `search.patentsview.org` does not exist: both the system resolver and the public resolvers 1.1.1.1 and 8.8.8.8 answer NXDOMAIN (DoH status 3). The legacy hosts `api.patentsview.org` and `patentsview.org` now serve the USPTO Open Data Portal single-page application instead of any PatentsView API reference. The legacy PatentsView API was retired, no reachable request contract exists, and no endpoint or parameter is invented to keep the candidate alive. | NXDOMAIN from `Resolve-DnsName -Server 1.1.1.1` and Cloudflare DoH; `GET https://api.patentsview.org/patents/query` returns the ODP index HTML (observed with TLS verification disabled; the chain also failed verification on the first live probe). |
| uspto-patent-assignment (dropped as a separate search API, implemented through the ODP route instead) | The plan's candidate is a search by patent number, assignor or assignee. The recovered verification note records that assignment records migrated to the USPTO Open Data Portal at the application-number-keyed route `/api/v1/patent/applications/{applicationNumberText}/assignment`, which this composite implements as the uspto-patent-assignment sub-source. The old standalone host publishes no reachable assignor/assignee search contract. | `GET https://assignment-api.uspto.gov/patent/lookup?query=test` fails with `getaddrinfo failed`; `assignment-api.uspto.gov` and `assignment.uspto.gov` return no A/AAAA/CNAME/NS answer from the system resolver, 1.1.1.1, 8.8.8.8 or Cloudflare DoH. The ODP assignment route answers HTTP 401 (route exists, key required). |
| google-patents-bigquery | The Google Patents public dataset is reachable only through BigQuery. BigQuery requires a Google Cloud project authenticated with Application Default Credentials or a service-account key, and the documentation assumes the `google-cloud-bigquery` client library; Google documents no unauthenticated or free-key HTTP path to `bigquery-public-data.google_patents`. The runner uses the Python standard library only, and the docker image installs no third-party package, so the candidate is dropped rather than adding a dependency or an unverifiable auth path. | The direct BigQuery REST path `https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/queries` answers HTTP 404 keyless; every documented access path starts with project authentication. |
| euipo-esearch-plus | EUIPO exposes its trademark and design APIs only through the EUIPO API Portal, which requires an account, a sandbox access request and a separate production-access application under the EUIPO conditions of use ("you will need to register for an account and request access to our sandbox environment ... you will need to apply for access to production"). There is no free-key or unauthenticated search endpoint, so the approval path cannot be completed here and no public request contract can be verified. | The API page `https://euipo.europa.eu/ohimportal/en/api` answered HTTP 403; the `copla` trademark and design data endpoints reset the connection (WinError 10054); the portal at https://dev.euipo.europa.eu/ is reachable and states the sandbox/production approval workflow. |

## Overlap with the plan's `research_discovery` row

`docs/BATCHING_PLAN.md` lists a separate `research_discovery` composite whose sub-sources include **EPO OPS** and **Google Patents Public Datasets**. This `patents_trademarks` composite absorbs those two rows as follows:

- **EPO OPS** is implemented here as the `epo-ops` sub-source (token endpoint, OAuth 2.0 client credentials, `published-data/search?q=`). The `research_discovery` row must not implement EPO OPS again.
- **Google Patents Public Datasets** appears here as the dropped candidate `google-patents-bigquery`. It is reported once per run as a documented skip. The `research_discovery` row has no Google Patents implementation to duplicate because none is possible without BigQuery authentication and a third-party client library.
- The remaining `research_discovery` sub-sources (Unpaywall, OpenAIRE Graph) are **not** touched by this composite. The plan's status table records that Unpaywall was already dropped and OpenAIRE was merged into `academic_search`, so no work is duplicated here.

The parent has verified that none of the seven candidates is already live in `PROJECT_MANIFEST.json`. The batch plan's `patents_trademarks` row names five sub-sources (PatentsView, USPTO Open Data Portal, USPTO Patent Assignment Search, USPTO TSDR, EUIPO eSearch plus); this adapter implements the four that have a verifiable contract and reports the other three as documented skips.

## Phase A keyless probe results (verbatim)

One script (`ci/probe_patents_trademarks_candidates.py`) issued a single keyless GET against each candidate's documented API endpoint and each candidate's official documentation URL and printed the HTTP status, the Content-Type header and a short body head. `status=0` means the request failed at the network or DNS layer. The script was run once on 2026-10-15.

```
Phase A patents_trademarks candidate probe
UTC 2026-10-15T19:56:39.610122+00:00
====================================================================================================
[patentsview] (api) https://search.patentsview.org/api/v1/patent/
    status=0 content-type=''
    body='URLError: <urlopen error [Errno 11001] getaddrinfo failed>'
[patentsview] (api-legacy) https://api.patentsview.org/patents/query
    status=0 content-type=''
    body='URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired (_ssl.c:1081)>'
[patentsview] (docs) https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
    status=0 content-type=''
    body='URLError: <urlopen error [Errno 11001] getaddrinfo failed>'
[patentsview] (key-request) https://patentsview.org/apis/keyrequest
    status=0 content-type=''
    body='URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired (_ssl.c:1081)>'
[uspto-open-data] (api) https://api.uspto.gov/api/v1/patent/applications/search?q=test
    status=401 content-type='application/json'
    body='{"message":"Unauthorized"}'
[uspto-open-data] (docs) https://data.uspto.gov/apis
    status=200 content-type='text/html'
    body='<!doctype html> <html lang="en" data-beasties-container> <head><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin> <meta charset="utf-8"> <base href="/"> <meta name="viewport" content="width=device-width'
[uspto-open-data] (query-spec) https://data.uspto.gov/documents/documents/ODP-API-Query-Spec.pdf
    status=200 content-type='text/html'
    body='<!doctype html> <html lang="en" data-beasties-container> <head><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin> <meta charset="utf-8"> <base href="/"> <meta name="viewport" content="width=device-width'
[uspto-patent-assignment] (api) https://assignment-api.uspto.gov/patent/lookup?query=test
    status=0 content-type=''
    body='URLError: <urlopen error [Errno 11001] getaddrinfo failed>'
[uspto-patent-assignment] (docs) https://developer.uspto.gov/api-catalog/patent-assignment-search-api
    status=200 content-type='text/html'
    body='<!doctype html> <html lang="en" data-beasties-container> <head><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin> <meta charset="utf-8"> <base href="/"> <meta name="viewport" content="width=device-width'
[uspto-tsdr] (api) https://tsdrapi.uspto.gov/ts/cd/casestatus/sn78787878/info.json
    status=401 content-type='text/plain;charset=UTF-8'
    body='Beginning October 2, you_ll need to register for an API key to download bulk data from our TSDR APIs. Register for an API key at https://account.uspto.gov/api-manager/. Learn more about this new requirement at https://de'
[uspto-tsdr] (docs) https://developer.uspto.gov/api-catalog/tsdr-data-api
    status=200 content-type='text/html'
    body='<!doctype html> <html lang="en" data-beasties-container> <head><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin> <meta charset="utf-8"> <base href="/"> <meta name="viewport" content="width=device-width'
[epo-ops] (api) https://ops.epo.org/3.2/rest-services/published-data/search?q=pa%3D%22test%22
    status=403 content-type='application/xml'
    body='<error><code>403</code><message>This request has been rejected due to the violation of Fair Use policy</message><moreInfo>https://www.epo.org/service-support/ordering/fair-use.html</moreInfo></error>'
[epo-ops] (auth) https://ops.epo.org/3.2/auth/accesstoken
    status=404 content-type='application/xml'
    body=''
[epo-ops] (docs) https://developers.epo.org/
    status=200 content-type='text/html; charset=utf-8'
    body='<!DOCTYPE html PUBLIC "-//W3C//DTD HTML+RDFa 1.1//EN"> <html lang="en" dir="ltr" version="HTML+RDFa 1.1" ...'
[google-patents-bigquery] (api) https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/queries
    status=404 content-type='text/html; charset=UTF-8'
    body='<!DOCTYPE html> <html lang=en> <meta charset=utf-8> <meta name=viewport content="initial-scale=1, minimum-scale=1, width=device-width"> <title>Error 404 (Not Found)!!1</title> ...'
[google-patents-bigquery] (docs) https://cloud.google.com/bigquery/public-data/google-patents
    status=404 content-type='text/html; charset=utf-8'
    body='<!doctype html> <html lang="en" dir="ltr"> ...'
[euipo-esearch-plus] (api) https://euipo.europa.eu/copla/trademark/data/?query=test
    status=0 content-type=''
    body='ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host'
[euipo-esearch-plus] (docs) https://euipo.europa.eu/ohimportal/en/api
    status=403 content-type='text/html'
    body='<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd"> <HTML><HEAD><META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=iso-8859-1"> <TITLE>ERROR: The request could ...'
```

Additional probes that confirmed or refuted a contract after the single Phase A run:

| Probe | Result |
|---|---|
| `GET https://api.uspto.gov/api/v1/patent/applications/search?q=test` (no key) | HTTP 401 `{"message":"Unauthorized"}` — route exists, key required. |
| Same URL with a bogus `X-API-KEY: bogus` header | HTTP 403 `{"message":"Forbidden"}` — the header name is correct (a wrong header name still answers 401). |
| `GET https://api.uspto.gov/api/v1/patent/applications/14412875/assignment` | HTTP 401 — the ODP assignment route exists. |
| `GET https://api.uspto.gov/api/v1/trademark/applications/search?q=test` | HTTP 403 `{"message":"Missing Authentication Token"}` — no such ODP trademark search route, so the adapter claims none. |
| `POST https://ops.epo.org/3.2/auth/accesstoken` with dummy Basic credentials | HTTP 401 `<error><code>401</code><message>ClientId is Invalid</message></error>` — the token endpoint and the client-credentials flow are confirmed. |
| `Resolve-DnsName search.patentsview.org -Server 1.1.1.1` | NXDOMAIN ("DNS name does not exist"). |
| `Resolve-DnsName assignment-api.uspto.gov -Type A -Server 1.1.1.1` | No answer (no A, AAAA, CNAME, NS or SOA record from the system resolver, 1.1.1.1, Google DoH or Cloudflare DoH). |
| `GET https://tsdrapi.uspto.gov/ts/cd/casestatus/sn78787878/info.json` | HTTP 401 with the USPTO message that an API key is required since October 2. |

## Version pins

None of the four implemented sub-sources is a locally installed tool, so there is no artefact to pin. The image is `python:3.13-slim-bookworm` and the versioned API surfaces used are the USPTO Open Data Portal API v1 (`/api/v1/`), the USPTO TSDR API v1 and the EPO Open Patent Services v3.2. No version was invented. This adapter's own descriptor is pinned at `version_pin="1.0"`.

## Notes

- **--health never touches the network.** `docker run --rm --network none <image> --health` prints exactly `ok` on stdout and an inventory JSON line on stderr listing each sub-source, its kind (`http_api` or `dropped`), its endpoint and whether its credential environment variable is configured, with `"network_used": false`. It opens no socket and reads no secret value into the output (only a boolean).
- **Secrets are never printed or recorded.** The ODP key travels only in the `X-API-KEY` header, the TSDR key only in the `USPTO-API-KEY` header, and the EPO OPS key and secret only in the `Authorization: Basic` header of the token request. The recorded `endpoint@ values contain no credential.
- **One request per sub-source per run.** The runner issues at most one HTTP request per implemented sub-source (four requests total) plus one EPO OPS token request, and never paginates. Each sub-source is truncated to 25 records with the untruncated count recorded in `record_count` / `total_result_count`.
- **A hit is not a conclusion.** A patent or trademark register record is a source observation, not proof of ownership, inventorship or use; every finding must be reviewed against the published register before it is relied on.
