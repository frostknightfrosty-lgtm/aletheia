# Rate Limits for corporate_registry Batch Adapter Sub-Sources

Each sub-source's documented rate limit, quoted from the provider's official documentation. Where a provider publishes no numeric limit, this file says **not published** rather than inventing a number.

| Sub-source | Endpoint | Auth | Rate limit | Official docs |
|---|---|---|---|---|
| Companies House (UK) | GET https://api.company-information.service.gov.uk/search/companies?q={term} | HTTP Basic; API key as username with an empty password (env COMPANIES_HOUSE_API_KEY) | 600 requests per 5 minutes | https://developer.company-information.service.gov.uk/developer-guidelines |
| NZBN (NZ) | GET https://api.business.govt.nz/gateway/nzbn/v5/entities?search-term={term} | Header Ocp-Apim-Subscription-Key (env NZBN_API_SUBSCRIPTION_KEY) | not published | https://portal.api.business.govt.nz/api/nzbn |
| KVK Open Dataset (NL) | GET https://opendata.kvk.nl/api/v1/hvds/basisbedrijfsgegevens/kvknummer/{kvknummer} | None (free, no key) | 1 request per minute per IP; also a general 200 requests per 5 minutes across all users | https://developers.kvk.nl/documentation/open-dataset-basis-bedrijfsgegevens-api |
| KVK Zoeken (NL) | GET https://api.kvk.nl/api/v2/zoeken?naam={name} | Header apikey (env KVK_API_KEY) | 300,000 queries per month; maximum 100 queries per second | https://developers.kvk.nl/documentation/zoeken-api |
| recherche-entreprises (France, official DINUM API surfacing RNE data) | GET https://recherche-entreprises.api.gouv.fr/search?q={term} | None (free, no key) | 7 requests per second per IP; 30 requests per second per ASN | https://recherche-entreprises.api.gouv.fr/docs |
| INPI RNE (France) | UNSUPPORTED - no endpoint implemented | n/a | n/a | https://data.inpi.fr/content/editorial/Acces_API_Entreprises |
| ASIC (Australia) | UNSUPPORTED - no endpoint implemented | n/a | n/a | https://www.asic.gov.au/online-services/information-for-intermediaries/application-programming-interfaces-apis |
| CIPC (South Africa) | UNSUPPORTED - no endpoint implemented | n/a | n/a | https://eservices.cipc.co.za/ |

---

**Notes:**

- **NZBN rate limit: not published.** The NZBN portal documents the API surface but publishes no numeric request quota, so none is claimed here. Implement conservative backoff on 429/5xx responses.
- **KVK Zoeken is a paid subscription and excludes private use.** The runner skips it unless KVK_API_KEY is set, and it is never a default enabled dependency. Its skip reason states that this sub-source is a paid subscription excluding private use.
- **KVK Open Dataset is a number lookup only** (no name search). The runner uses the input value as the kvknummer path segment and does not invent a name-search endpoint.
- **INPI RNE, ASIC and CIPC are unsupported** and are always reported as skipped with these exact reasons:
  - inpi-rne: "INPI RNE exposes no documented free search API (bulk SFTP and dataset APIs only)"
  - asic: "ASIC publishes no public JSON search API; ASIC Connect is web-only and DSP applications are closed until 2027"
  - cipc: "CIPC provides no public API; enterprise search is web-only"
- Companies House credentials are sent only in the HTTP Basic Authorization header, built locally as base64 of "key:"; the key is never printed or included in runner output.
- The adapter queries each sub-source at most once per run (8 sub-sources, of which 3 are documented skips), so per-run quota consumption is minimal.
- Rate-limit headers (Retry-After, X-RateLimit-*) should be parsed and honored where present.
