# Rate Limits, Authentication, Formats and Pins for the email_auth Batch Adapter Sub-Sources

Every endpoint, query-parameter name, authentication requirement, documented limit, response format and documentation URL below was read from the sub-source's own official documentation (the scan.mx API page at https://api.scan.mx/ and the checkdmarc API reference at https://domainaware.github.io/checkdmarc/api.html), or confirmed against the live sub-source endpoint. Where a source publishes no numeric limit that could be verified from a reachable official page this file says **not published** rather than inventing a number. No endpoint, parameter name, function name or version here was inferred from an example response, and no candidate was kept alive by guessing a contract.

**Neither sub-source publishes an environment-variable name because neither sub-source needs a credential.** scan.mx is keyless with no signup, and checkdmarc queries DNS directly from inside the image. The descriptor therefore declares `secret_env=[]`, this adapter configures no environment variable, and no secret is ever printed or recorded.

## Sub-source summary (implemented)

| Sub-source | Base URL / module and exact endpoint or entry point (verbatim from the vendor's docs) | Parameters | Auth | Documented limit | Format | Official docs URL |
|---|---|---|---|---|---|---|
| scan-mx | `GET https://api.scan.mx/v1/check?domain=example.com` | `domain` (the domain to check); the optional `&smtp=1` queues the live SMTP probe (not used by this adapter). The stream endpoint is `GET /v1/check/stream?domain=` (also not used). | **None.** The API page states "No API key, no authentication, no signup." | **not published.** The API page states reports are cached (up to 30 days) and "rate-limited per IP and per (IP, domain) for abuse prevention"; HTTP 429 `rate_limited` carries a `Retry-After` header, and `rescan_capped` is answered when a domain hits "the hourly forced re-scan cap". No numeric request rate is published. | JSON (the SSE stream endpoint is `text/event-stream` and is not used) | https://api.scan.mx/ |
| checkdmarc | module `checkdmarc`; documented entry point `checkdmarc.check_domains(domains, *, ...)`. The per-section functions `checkdmarc.smtp.check_mx`, `checkdmarc.spf.check_spf` and `checkdmarc.dmarc.check_dmarc` are also documented. This adapter calls `checkdmarc.check_domains([domain])` and reads its `mx`, `spf` and `dmarc` keys. | `domains` (a list of domain names); documented keyword arguments include `check_mx_tls`, `nameservers`, `resolver`, `timeout`, `retries`, `wait` and `bimi_selector`. The adapter passes only the domain and uses the documented defaults. | **None.** checkdmarc is a local library and queries the DNS resolvers directly; its documentation names no credential or API key. | **not published.** checkdmarc publishes no request limit because it queries DNS directly rather than through a rate-limited API; its `timeout` (default 2.0 s) and `retries` (default 0) keywords bound each query. | Python objects (a `DomainCheckResult`, which is a `dict` at runtime); `checkdmarc.results_to_json` serialises one to JSON | https://domainaware.github.io/checkdmarc/api.html |

## scan-mx — scan.mx email authentication and deliverability API

- **Endpoint (verbatim from the API page's Quick start):** `GET https://api.scan.mx/v1/check?domain=example.com`. The page also documents `GET https://api.scan.mx/v1/check/stream?domain=example.com` for the live SMTP probe over Server-Sent Events; this adapter queries only the JSON check endpoint, once per run, and never the stream endpoint.
- **Exact parameter name:** `domain`. The optional `smtp=1` parameter is documented but not sent, so no live SMTP probe is queued.
- **Auth:** none. The API page states: "No API key, no authentication, no signup." There is no account, key request or environment variable.
- **Documented limit:** not published as a reachable number. The API page states: "Reports are cached (up to 30 days) and rate-limited per IP and per (IP, domain) for abuse prevention." The documented error responses are HTTP 403 `opted_out` (the domain owner blocked scanning), HTTP 422 `invalid_domain`, HTTP 424 `domain_not_configured`, HTTP 429 `rate_limited` ("Too many requests. Check the Retry-After header.") and HTTP 429 `rescan_capped` ("This domain hit the hourly forced re-scan cap"). No requests-per-minute/hour number is published.
- **Format:** JSON. The documented response object carries `domain`, `grade`, `score`, `provider`, `smtp_status`, `sections` (per-section score/grade), `checks` (id, section, status, severity, message, rfc, details), `permalink` and `expires_at`; a domain with no email records still returns HTTP 200 with `email_configured: false`. A successful live probe also populates `smtp_status` and the adapter records the first `MAX_CHECKS` (50) checks.
- **Docs URL:** https://api.scan.mx/ (linked from https://scan.mx/ as "Read the API docs"). The MCP surface at https://api.scan.mx/mcp is documented separately and is not used by this adapter.
- **Data handling noted by the API page:** reports are stored in an EU database and cached for up to 30 days; request metadata is logged for abuse prevention. The runner stores only the fields it normalises and never writes the raw response to disk.

## checkdmarc — Python library for validating SPF, DMARC and MX records

- **Module and documented entry point:** the package is imported as `checkdmarc` and the documentation's top-level API reference lists `class checkdmarc.DomainCheckResult` and `checkdmarc.check_domains(domains, *, ...) -> DomainCheckResult | list[DomainCheckResult]`. Calling it with a single-element list returns a single `DomainCheckResult`; the documented result keys are `domain`, `base_domain`, `dnssec`, `soa`, `ns`, `mx`, `spf`, `dmarc`, `smtp_tls_reporting` and (optional) `bimi`. The per-section functions `checkdmarc.smtp.check_mx`, `checkdmarc.spf.check_spf` and `checkdmarc.dmarc.check_dmarc` are also documented and share the same result shapes. **checkdmarc is therefore importable as a library, not CLI-only, so it is not dropped.**
- **Exact call this adapter makes:** `checkdmarc.check_domains([domain])` with no keyword arguments, so the documented defaults apply (in particular `check_mx_tls=False` — no STARTTLS/TLS probe is made — and `bimi_selector="default"`). The runner reads the `mx`, `spf` and `dmarc` keys and stores them verbatim.
- **Auth:** none. checkdmarc is a local library that queries DNS resolvers directly; its documentation lists no credential, API key or account.
- **Documented limit:** not published (no numeric request limit exists for a local DNS-querying library). The documented `timeout` (default 2.0 seconds) and `retries` (default 0) keywords bound each DNS query, and the adapter uses those defaults.
- **Format:** Python mapping at runtime (`DomainCheckResult` is a `TypedDict`); `checkdmarc.results_to_json` returns a JSON string and `checkdmarc.results_to_csv` a CSV string.
- **Version pin:** `checkdmarc==6.0.4`, read from the PyPI JSON API at https://pypi.org/pypi/checkdmarc/json (`info.version` = "6.0.4", matching `release_url` https://pypi.org/project/checkdmarc/6.0.4/). The same record reports `license_expression` "Apache-2.0", `requires_python` ">=3.10" and a classifier for "Programming Language :: Python :: 3.14". The recovered plan note named 6.0.3; the live PyPI record checked here is 6.0.4, which is the version pinned.
- **Docs URL:** https://domainaware.github.io/checkdmarc/api.html (project page: https://pypi.org/project/checkdmarc/; source: https://github.com/domainaware/checkdmarc).

## Dropped candidates

**None.** Both candidates named for the email_auth batch were verified from their own official documentation and are implemented:

- **scan-mx** publishes a keyless HTTPS JSON endpoint, its exact `domain` query parameter and its documented error responses on https://api.scan.mx/, so it is implemented as the `scan-mx` sub-source.
- **checkdmarc** publishes an importable library API (`checkdmarc.check_domains` plus the per-section `check_mx`, `check_spf` and `check_dmarc` functions) on https://domainaware.github.io/checkdmarc/api.html, so it is implemented as the `checkdmarc` sub-source; it is not CLI-only.

No endpoint, query parameter, function name or version is invented, and the runner's `UNSUPPORTED_SUB_SOURCES` map is empty. Any candidate added to it in future is reported once per run as a documented skip carrying the recorded reason.

## Phase A probe result for scan-mx (verbatim)

One keyless GET was issued to the documented check endpoint on 2026-10-15 with a plain `urllib.request` call and a named user agent (`Aletheia/0.9.0 (email-auth phase-A probe)`); the response was written to a temporary file and the head printed. The query used the vendor's own example domain.

`GET https://api.scan.mx/v1/check?domain=gmail.com`

```
URL: https://api.scan.mx/v1/check?domain=gmail.com
STATUS: 200
CONTENT-TYPE: application/json
RETRY-AFTER: None
LEN: 22502
BODY-HEAD: {
  "domain": "gmail.com",
  "grade": "B",
  "score": 89,
  "provider": "google.com",
  "email_configured": true,
  "smtp_status": "complete",
  "sections": {
    "mx": {
      "score": 100,
      "grade": "A"
    },
    "provider": {
      "score": 100,
      "grade": "A"
    },
    "spf": {
      "score": 100,
      "grade": "A"
    },
    "dkim": {
      "score": 100,
      "grade": "A"
    },
    "dmarc": {
      "score": 94,
      "grade": "A"
    },
    "dns": {
      "score": 97.5,
      "grade": "A"
    },
    "blacklist": {
      "score": 100,
      "grade": "A"
    },
    "bulk": {
      "score": 94,
      "grade": "A"
    },
    "mtasts": {
      "score": 100,
      "grade": "A"
    },
    "tls": {
      "score": 100,
      "grade": "A"
    },
    "bimi": {
      "score": 100,
      "grade": "A"
    },
    "smtp": {
      "score": 97.5,
      "grade": "A"
    }
  },
  "checks": [
    {
      "id": "mx.presence",
      "section": "mx",
      "status": "pass",
      "severity": "info",
      "message": "5 MX record(s) found.",
      "rfc": null,
      "details": {
        "records": [
          {
            "preference": 5,
            "exchange": "gmail-smtp-in.l.google.com",
            "ttl": 668
          },
          {
            "preference": 10,
            "exchange": "alt1.gmail-smtp-in.l.google.com",
            "ttl": 668
          },
          {
            "preference": 20,
            "exchange": "alt2.gmail-smtp-in.l.google.com",
            "ttl": 6
```

The probe's top-level JSON keys were exactly: `domain`, `grade`, `score`, `provider`, `email_configured`, `smtp_status`, `sections`, `checks`, `permalink`, `created_at`, `updated_at`, `expires_at`. This confirms the documented base URL (`https://api.scan.mx`), path (`/v1/check`), exact query parameter (`domain`), keyless access, JSON response format and the documented response shape. The probe is the only live request this adapter's Phase A made to scan.mx.

checkdmarc was verified from documentation only (its own API reference and the PyPI JSON record); no DNS query was issued by this adapter's Phase A, so no captured checkdmarc result appears here.

## Version pins

- **scan-mx:** no locally installed artefact; the vendor publishes the API without a version number in the documented path (`/v1/`) and the base URL is `https://api.scan.mx`. No version was invented.
- **checkdmarc:** `checkdmarc==6.0.4` from PyPI (https://pypi.org/pypi/checkdmarc/json), installed by `docker/email_auth/Dockerfile`. This adapter's own descriptor is pinned at `version_pin="1.0"`.

## Notes

- **--health never touches the network.** `docker run --rm --network none <image> --health` prints exactly `ok` on stdout and an inventory JSON line on stderr listing each sub-source, its kind (`http_api` or `library`), its endpoint or module and a `usable` boolean, with `"network_used": false`. For checkdmarc the `usable` flag comes from `importlib.util.find_spec` and the module is not imported by --health. No socket is opened.
- **The checkdmarc import is lazy.** It lives inside `query_checkdmarc`, so the image still answers `--health` if the package were missing and a run reports the missing import as a documented skip rather than crashing.
- **One request per sub-source per run.** The runner issues at most one HTTPS request to scan.mx and makes one `checkdmarc.check_domains` call; scan.mx results are cached server-side for up to 30 days, and the adapter never paginates or forces a re-scan.
- **A record is not a reputation verdict.** MX, SPF and DMARC records describe published mail configuration. A missing record or a low grade is a source observation, not proof of spoofing, compromise or intent, and every finding must be reviewed against the published DNS records before it is relied on.
