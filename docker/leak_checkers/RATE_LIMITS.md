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

## Broń Vault (operator-run local instance)

- First-party repository: https://github.com/ITSEC-Research/bron-vault (Apache-2.0).
- Contract pin: release v1.4.0, commit `6bfdcc0196ac90ed38a35a1099697497680c1666`. The contract below is read from that release's route source (`app/api/v1/search/credentials/route.ts`) and its auth module (`lib/api-key-auth.ts`).
- Request: `POST {BRON_VAULT_URL}/api/v1/search/credentials` with JSON body `{"query": <value>, "type": "email"|"username"|"any", "page": 1, "limit": 25, "includePasswords": false}`. `type` is `email` for email inputs, `username` for username inputs, and `any` for every other input type. Full passwords are never requested.
- Authentication: `X-API-Key: bv_<random>` header; the key is created on the operator's own instance's API Keys page, is read from `BRON_VAULT_API_KEY`, and is never put in the URL or output.
- Conflicting surfaces: the project README names `GET /api/v1/search/credentials`, but the route file shipped in the pinned release implements `POST`; this runner follows the route file, and the discrepancy is recorded here as required.
- Response: `{"success": true, "data": {"credentials": [...], "pagination": {...}}, "meta": {...}}`. The runner keeps at most 25 credential records, records the masked password only (`passwordMasked`), and never stores a full password.
- Local-instance-only rule: only a configured loopback address (`localhost`, `*.localhost`, `127.0.0.0/8`, `::1`) or Docker's documented `host.docker.internal` alias is accepted; any other `BRON_VAULT_URL` host is refused before a socket is opened, redirects that would leave the local host are refused, and requests bypass all proxy environment variables, so a query cannot leave the operator's machine. This runner never deploys the application, never uploads log archives, and never asks anyone to expose an instance to the internet.
- When `BRON_VAULT_URL` or `BRON_VAULT_API_KEY` is unset, the source reports the documented skip: the operator runs the instance themselves and the logs it parses are local stealer-log archives they uploaded to their own instance.
- Self-test: `--selftest-bron-vault` exercises the client path against a loopback stub implementing the pinned route contract (auth header, success envelope parsed into a record, 401 refusal, non-loopback refusal). The stub is test scaffolding and is never presented as the real application.
- Rate limit: at most one request per run, sent directly to the loopback instance and never through the egress proxy.

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

## Runner constraints

- Secrets are only sent in documented headers; health output and structured results never include secret values.
- At most one request per supported source is made per run, with no pagination and a 25-record normalization cap.
- Unsupported candidates are emitted as explicit skips with the evidence boundary/reason above. No unverified endpoint is probed.
