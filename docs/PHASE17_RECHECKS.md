# Phase 17 Wave-A live re-checks (2026-10-18)

Inventory rows in [`SOURCE_COMPLETENESS.md`](SOURCE_COMPLETENESS.md) §A whose
state depends on vendor facts carry a "re-check" path. This file is the dated
evidence record of those live re-checks. Probes were run from the campaign
workstation on **2026-10-18**; DNS answers are the tool-reported
`Resolve-DnsName` records and HTTP results are the tool-observed outcomes.
Nothing here is inferred: an item that could not be verified stays recorded as
unverified, and re-opens only on a vendor change.

## #28 PatentsView — legacy API host is dead; successor needs a USPTO account

- `Resolve-DnsName search.patentsview.org` → **NO DNS RECORD** (the name does
  not exist; the apex `patentsview.org` still resolves to Cloudflare IPs).
- `GET https://search.patentsview.org/` → no HTTP response (transport error).
- rOpenSci tech note (2026-03-10,
  <https://ropensci.org/blog/2026/03/10/patentsview-breaking-release/>),
  verbatim:
  > the PatentsView API team had made breaking changes and obsoleted the
  > original API (all calls to the original endpoints return 410 Gone)

  > In late February they replaced their forum with a message saying the page
  > was temporarily unavailable. Further, they have also removed the link to
  > request an API key, so it's unclear whether they'd honor requests for API
  > keys using the link below. Nothing has been officially announced but the
  > long term viability of the API seems uncertain.
- USPTO transition guide (search-result snippet, `data.uspto.gov`):
  "API keys for accounts that did not complete these fields by October 8,
  2026, have been deactivated." — the successor route is the USPTO Open Data
  Portal behind an account with identity fields, not an anonymous key.
- **Outcome:** the recorded drop reason ("API host no longer resolves") is
  re-confirmed with fresh evidence. A successor route exists only behind a
  free USPTO portal account — owner action recorded. No endpoint contract is
  readable without that account, so no adapter code is written against a
  guessed host.

## #27 ERATV — no public SPARQL/RDF endpoint; browser-only registry

- `Resolve-DnsName data.era.europa.eu` → **SOA** (NXDOMAIN: the presumed
  Knowledge-Graph host does not exist in DNS).
- `GET https://data.era.europa.eu/` → no HTTP response (transport error).
- `GET https://eratv.era.europa.eu/` → the ERATV browser application loads
  (search and advanced-search forms, "View Registered Authorisations", Terms
  of Use); no API, SPARQL or RDF link is offered.
- **Outcome:** the blocker recorded in `transport_asset_registry.py` stands —
  the register is browser-hosted and no public SPARQL/RDF service is a
  verified ERATV data endpoint. Re-open on any ERA publication of a
  machine-readable endpoint.

## #29 Google Patents Public Datasets — no-billing route exists (sandbox)

- <https://cloud.google.com/bigquery/docs/sandbox> verbatim:
  > The BigQuery sandbox lets you experience BigQuery without providing a
  > credit card or creating a billing account for your project.
- **Outcome:** the nothing-paid route exists (BigQuery sandbox). Querying the
  public `patents-public-data` datasets still requires a Google-account access
  token, which is an owner-provided configuration value. The build (a
  `google_patents` sub-source over the documented BigQuery REST `jobs.query`
  endpoint, with a skip-without-token path) is queued in this P17.11 wave.

## #32 Google Custom Search JSON API — closed to new customers

- <https://developers.google.com/custom-search/v1/overview> verbatim (page
  "Last updated 2026-02-18 UTC"):
  > Note: The Custom Search JSON API is closed to new customers. Vertex AI
  > Search is a favorable alternative for searching up to 50 domains.
  > …Existing Custom Search JSON API customers have until January 1, 2027 to
  > transition to an alternative solution.

  > This API is not available for new customers.
- **Outcome:** unavailable for this project; stays out. The class is carried
  by integrated sub-sources: `search_engines` queries **marginalia** and the
  **common-crawl-index** (confirmed in
  `app/aletheia/adapters/search_engines.py`).

## #35 PublicWWW — no free tier surfaced; stays out under nothing-paid

- `GET https://publicwww.com/pricing.html` → the vendor serves a browser
  verification wall ("Checking your browser before continuing"); no free tier
  appears on the page; footer © 2005-2026.
- **Outcome:** the recorded reason ("vendor docs require a paid plan") is not
  contradicted and no free tier surfaced. Stays out with this evidence;
  re-open only on a vendor free-tier change.

## #33 Unpaywall — DOI-keyed endpoint live; email parameter enforced

- `GET https://api.unpaywall.org/v2/10.1038/nature12373?email=contact@example.com`
  → **HTTP 422** (the endpoint answers; the request with a placeholder contact
  address was refused).
- The official product page (<https://unpaywall.org/products/api>) served no
  readable content to the fetcher during this review, so no rate-limit number
  is quoted here; the adapter records "not readable at review" rather than a
  guessed number.
- **Outcome:** build the live DOI path in the `academic_search` runner
  (this P17.11 unit): DOI-shaped input → `GET /v2/{doi}` with the
  `UNPAYWALL_EMAIL` contact secret; every other input keeps the documented
  skip. The contact email is an owner-provided secret (no registration).

## #36 CipherScan — next re-check in this wave

- Path per the inventory: pin a specific commit SHA as the verifiable
  artifact. Not yet probed; recorded here when its build unit runs.
