# Leak checkers: contracts and limits

## LeakIX

- First-party API search docs: https://docs.leakix.net/docs/api/search/
- Authentication docs: https://docs.leakix.net/docs/api/authentication/
- Request: `GET https://leakix.net/search` with `scope=leak`, `q=<URL-encoded query>`, and `page=0`.
- Authentication: `api-key: <key>` header. The key is generated in the user's LeakIX profile; it is read from `LEAKIX_API_KEY` and is never put in the URL or output.
- Response: JSON array of l9events. The runner keeps only event identifiers, host/IP, port, time, source/type, and allowlisted leak classification/count fields. It drops raw summaries and credential-like fields.
- Rate limit: LeakIX documents approximately 1 request/second and requires clients to honor `x-limited-for` after HTTP 429. This runner makes at most one request per investigation and does not paginate.
- Cap: response body is limited to 2 MiB; at most 25 records are normalized.

## GrayhatWarfare

- First-party API v2 docs: https://buckets.grayhatwarfare.com/docs/api/v2
- Search endpoint: `GET https://buckets.grayhatwarfare.com/api/v2/files`
- Request parameters: `keywords=<query>`, `limit=25`, `start=0`. These are documented search parameters; no scrolling or later pages are requested.
- Authentication: `Authorization: Bearer <apiKey>` header. The vendor documents API access for a free registered account; the token is read from `GRAYHATWARFARE_TOKEN` and is never put in the URL or output.
- Response: JSON object containing `meta.results` and `files`; the runner records at most 25 index metadata records and never fetches the returned file URLs.
- Limits: vendor documentation describes plan-dependent search/result restrictions, and the API page allows up to 1,000 files per page. No fixed free-account request quota is claimed here; this runner asks for 25 records and makes at most one request per investigation.
- Terms/pricing: https://grayhatwarfare.com/packages

## Dropped sources

### BreachDirectory

- First-party site: https://breachdirectory.org/
- That official site returned HTTP 403 during this contract review. No first-party API endpoint, parameters, authentication format, or response schema could be verified from the materials available in this review.
- Drop reason: contract-unverified. No endpoint or RapidAPI route is inferred. Reconsider only after first-party API documentation can be reviewed.

### Leak-Lookup

- First-party API page: https://leak-lookup.com/api (requires sign-in to view).
- First-party terms: https://leak-lookup.com/support/terms#use-of-service
- The terms restrict searches to the user's own information or people they are authorized in writing to search; they state that searching others without consent is prohibited.
- Drop reason: this adapter's request contract has no way to verify or retain the required written authorization, so it does not issue Leak-Lookup requests. This is a project integration limitation, not a claim that the vendor has no API.

### Broń Vault

- First-party repository: https://github.com/ITSEC-Research/bron-vault
- The README describes a self-hosted Docker application, local archive uploads, and API-key-authenticated local REST routes. It warns against exposing the deployment to public networks.
- Drop reason: integrating it would require deploying and managing a separate operator-owned store and uploading local log archives; this public-source composite does neither. It is not characterized here as offline-only or as lacking an API.

## Runner constraints

- Secrets are only sent in documented headers; health output and structured results never include secret values.
- At most one request per supported source is made per run, with no pagination and a 25-record normalization cap.
- Unsupported candidates are emitted as explicit skips with the evidence boundary/reason above. No unverified endpoint is probed.
