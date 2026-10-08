# Phase 6 — Corporate, Records, and Sanctions

## Implemented
- SEC EDGAR public REST data: company index + bounded recent filing metadata.
- GLEIF API v1: LEI search and basic parent/child metadata.
- OpenCorporates REST API v0.4.8: company search using an API token.
- OpenSanctions hosted API: sanctions-scoped text search only; API key required.
- CourtListener REST API v3 search: public case search, optionally authenticated.

## Legal controls
All Phase 6 network adapters require `authorization_assertion` and `legal_only=true`.
Secrets are inherited into Docker by environment variable name, never inserted into command argv.
The adapters do not submit filings, access private/sealed dockets, bypass authentication, or use PACER credentials.

## Evidence semantics
- SEC/GLEIF/OpenCorporates facts are source observations and retain source URLs and timestamps.
- OpenSanctions search score is explicitly *search relevance*, not identity probability or a confirmed sanctions hit.
- CourtListener search results are discovery leads; underlying court material must be reviewed before making a legal assertion.
