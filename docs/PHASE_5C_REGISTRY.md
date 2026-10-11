# Phase 5c Proposed Adapter Registry

Checked 2026-10-11. This is a source review, not an adapter implementation or live tool execution. The proposal text says “twenty” but names only 19 tools; no twentieth proposal was supplied, so none is invented.

For every proposal retained below, verification_status remains proposed-unverified: source existence and published facts were checked, but no Aletheia adapter has been built or run. “Verified” means the cited primary source was sufficient to verify the proposed tool/service or standard, not that Aletheia has verified-live evidence.

## Source-verified proposals — not registered

### gravatar

~~~yaml
name: gravatar
input_types: [email]
invocation: api  # hash lookup against public profile API
requires_key: false  # optional bearer token for the documented profile endpoint
legal_tier: 1
license: "Hosted API; no upstream client software license assigned"
last_commit: "not applicable to the API service"
fragility: "Profile lookup depends on the primary email hash; rate limits and profile availability can change."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://docs.gravatar.com/sdk/profiles/ | paid_status: free-with-limits | Public profile retrieval is documented; bearer authorization is optional and rate limiting applies."
batch_grouping: email_intel
~~~

The official guide documents profile retrieval by an email SHA-256 identifier and says the authorization header is optional. The profile API only resolves the primary address associated with an account.

### mr-holmes

~~~yaml
name: mr-holmes
input_types: [name, username, phone, domain]
invocation: local_python  # upstream Python script
requires_key: false  # optional WhoisXML API integration is separate
legal_tier: 2
license: GPL-3.0
last_commit: "2026-02-21"
fragility: "Broad collection and mixed public sources can change; built-in proxy and search functions must not be used to evade controls."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://github.com/Lucksi/Mr.Holmes | paid_status: free-with-limits | Repository and GPL-3.0 license verified; optional WhoisXML API requires its own account/key."
batch_grouping: people_search
~~~

The repository describes a Python OSINT script and lists domain, username, and phone use. It also documents proxy functionality and an optional WhoisXML API key. Any future wrapper must use only permitted public calls and must disable any proxy use intended to evade access controls. Repository API metadata showed the latest commit on 2026-02-21.

### onyphe

~~~yaml
name: onyphe
input_types: [domain, ip]
invocation: api
requires_key: true
legal_tier: 2
license: "Hosted service; API is subject to ONYPHE terms"
last_commit: "not applicable to hosted API"
fragility: "Category availability, result limits, and query behavior are service-controlled."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://search.onyphe.io/files/onyphecheatsheetfreeview.pdf | paid_status: free-with-limits | Free View describes free categories and API-token use; terms restrict the free view to individual use."
batch_grouping: domain_intel
secondary_batch_grouping: threat_intel
~~~

ONYPHE's official Free View sheet documents free categories and an API-token request example. The free path is limited; its terms and category restrictions must be followed. No Aletheia query or returned data was tested.

### ivre

~~~yaml
name: ivre
input_types: [domain, ip]
invocation: local_python  # self-hosted framework
requires_key: false
legal_tier: 2
license: GPL-3.0
last_commit: "2026-09-10"
fragility: "It can orchestrate active scanners; a future adapter must expose only approved passive/indexed or explicitly scoped operations."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://github.com/ivre/ivre | paid_status: free | Public repository and GPL-3.0 license verified; latest commit metadata was 2026-09-10."
batch_grouping: domain_intel
~~~

The official repository describes IVRE as a self-hosted network reconnaissance framework and documents integrations with active scanners. Source existence, license, and recent maintenance were verified; unrestricted scanner orchestration is not approved by this proposal.

### urlscan

~~~yaml
name: urlscan
input_types: [url, domain]
invocation: api
requires_key: true  # unauthenticated users have only minor quotas
legal_tier: 1
license: "Hosted service; API is subject to urlscan terms"
last_commit: "not applicable to hosted API"
fragility: "Schema fields may change; quotas and visibility settings apply."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://urlscan.io/docs/api/ and https://urlscan.io/pricing/ | paid_status: free-with-limits | Free API quota exists; broader quotas/features are paid."
batch_grouping: domain_intel
~~~

The official API documents search, scan submission, account/API-key use, and public/unlisted/private visibility. A future Aletheia adapter should search existing scans only by default; new submissions can disclose a URL publicly or cause a remote scan and require an explicitly reviewed scope. URLs containing personal data must not be submitted as public scans.

### rdap

~~~yaml
name: rdap
input_types: [domain, ip]
invocation: api  # standardized RDAP service discovery and queries
requires_key: false
legal_tier: 1
license: "Protocol and registry, not a specific client implementation; implementation license must be checked separately."
last_commit: "not applicable to the IANA bootstrap registry"
fragility: "Bootstrap data and registry endpoints can change; follow the current IANA registry."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://www.iana.org/assignments/rdap-dns | paid_status: free | IANA maintains the RDAP DNS bootstrap registry and references RFC 9224."
batch_grouping: domain_intel
~~~

RDAP is a protocol/service-discovery proposal rather than one identifiable software package. The IANA registry verifies the standards-based endpoint bootstrap; any selected client library still needs its own license and version review.

### threatcluster

~~~yaml
name: threatcluster
input_types: [keyword, domain, ip]
invocation: api
requires_key: true
legal_tier: 2
license: "Hosted service; API is subject to ThreatCluster terms"
last_commit: "not applicable to hosted API"
fragility: "Free-key allowance, response fields, and included dark-web content can change."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://threatcluster.io/pricing | paid_status: free-with-limits | Official pricing documents a no-card free key with 100 credits/day and read scopes including dark-web data."
batch_grouping: darkweb_search
secondary_batch_grouping: threat_intel
~~~

The verified free tier includes dark-web read scopes. That means a future adapter cannot pass through arbitrary snippets, extracted data, or victim-enrichment fields: its response must be reviewed and filtered to exclude plaintext credentials, stolen tokens, and criminal-market content before this proposal can be approved for implementation. The free service is described as for evaluation and personal use; commercial use and redistribution have separate plans/terms.

### social-analyzer

~~~yaml
name: social-analyzer
input_types: [username]
invocation: local_python  # API, CLI, and web app
requires_key: false
legal_tier: 2
license: AGPL-3.0
last_commit: "2026-01-12"
fragility: "Depends on platform-specific public endpoints and is likely to change or be throttled."
verification_status: proposed-unverified
source_verification: "verified: 2026-10-11 | source: https://github.com/qeeqbox/social-analyzer | paid_status: free-with-limits | Public source and AGPL-3.0 license verified; platform-level terms/rates still apply."
batch_grouping: social_media
~~~

The repository describes an API, CLI, and web app for finding public profiles across social sites. Repository API metadata showed the latest commit on 2026-01-12.

## Rejected on verification

### footprint-osint

~~~yaml
name: footprint-osint
input_types: [email, password, domain, username]
invocation: local_python
requires_key: false
legal_tier: 1  # proposed; not accepted
verification_status: proposed-unverified
verification: "rejected | reason: no exact authoritative project matching this proposal could be verified; the proposed password input also conflicts with the hard-floor boundary."
paid_status: unverified
~~~

The name resolves to generic or unrelated footprint projects; no exact upstream, license, current maintenance date, or free path was established.

### ghunt

~~~yaml
name: ghunt
input_types: [email]
invocation: local_python
requires_key: true  # requires Google account cookies/login
legal_tier: 4  # rejected hard-floor tier
license: AGPL-3.0
last_commit: "not independently retrieved in this source check"
verification_status: proposed-unverified
verification: "rejected | reason: the official CLI documents Google login and cookie-based authentication, which places the proposed access path at Tier 4."
paid_status: free-with-limits
~~~

Official sources: https://github.com/mxrch/GHunt and https://github.com/mxrch/GHunt/blob/master/ghunt/helpers/auth.py. The repository documents a login step and manual or companion-provided cookies. It is not eligible for the registry under the hard floor, even though the source is public and the tool itself is free.

### emailrep

~~~yaml
name: emailrep
input_types: [email]
invocation: api
requires_key: true
legal_tier: 5  # source includes dark-web credential leaks; rejected hard-floor tier
license: "Hosted API; no client software license"
last_commit: "not applicable to hosted API; provider docs updated about one month before this check"
verification_status: proposed-unverified
verification: "rejected | reason: provider documentation says new API keys are not being issued and lists dark-web credential leaks among its sources, placing the described data provenance at Tier 5."
paid_status: free-with-limits
~~~

Official sources: https://docs.sublime.security/reference/emailrep-introduction and https://emailrep.io/key. The service and API exist, but the provider does not issue new keys, and its own source description includes dark-web credential leaks. Both facts independently bar this proposal.

### nexus-osint

~~~yaml
name: nexus-osint
input_types: [username, email, domain, ip]
invocation: local_python
requires_key: unverified
legal_tier: 2  # proposed; not accepted
license: "No SPDX license asserted by the matching repository"
last_commit: "2026-09-13 for the unrelated repository found"
verification_status: proposed-unverified
verification: "rejected | reason: the exact proposed utility could not be disambiguated; the matching public repository found is an unrelated AI-native OSINT platform, not a verified tool matching this contract."
paid_status: unverified
~~~

The matching source inspected was https://github.com/sayan9168/nexus-osint. No exact invocation contract, license/version pin, rate limit, or maintenance state matching the proposal was verified.

### osint-search-tool

~~~yaml
name: osint-search-tool
input_types: [name, username, email, phone, address, domain, ip]
invocation: local_python
requires_key: unverified
legal_tier: 2  # proposed; not accepted
verification_status: proposed-unverified
verification: "rejected | reason: this generic name did not resolve to one authoritative upstream project with a matching contract."
paid_status: unverified
~~~

No exact license, current release, last-commit date, or invocation method could be verified without guessing which project was intended.

### vamp-darkweb-intel

~~~yaml
name: vamp-darkweb-intel
input_types: [domain, ip, keyword]
invocation: local_python
requires_key: unverified
legal_tier: 1  # proposed; not accepted
verification_status: proposed-unverified
verification: "rejected | reason: no authoritative exact upstream project or public API matching this name and contract was verified."
paid_status: unverified
~~~

No license, maintenance date, source provenance, or content-safety boundary was established.

### twint-fork

~~~yaml
name: twint-fork
input_types: [username, email, keyword]
invocation: local_python
requires_key: false
legal_tier: 2
license: MIT  # original project only
last_commit: "2021-03-02 for original upstream; repository archived 2023-03-30"
verification_status: proposed-unverified
verification: "rejected | reason: no specific maintained fork was named; the original upstream repository is archived and stale."
paid_status: free
~~~

The original repository is https://github.com/twintproject/twint and GitHub marks it archived on 2023-03-30. The original repository's broad scraping behavior is not a maintained or verified substitute for an unspecified fork.

### osintgram

~~~yaml
name: osintgram
input_types: [username]
invocation: local_python
requires_key: true  # Instagram login/session
legal_tier: 4  # rejected hard-floor tier
license: GPL-3.0
last_commit: "2026-09-28"
verification_status: proposed-unverified
verification: "rejected | reason: the identified upstream requires Instagram account authentication for its collection flow, which is Tier 4."
paid_status: free-with-limits
~~~

The inspected upstream is https://github.com/Datalux/Osintgram. A public username seed does not make a logged-in collection path eligible.

### deepground

~~~yaml
name: deepground
input_types: [keyword, image]
invocation: local_python
requires_key: unverified
legal_tier: 2  # proposed; not accepted
verification_status: proposed-unverified
verification: "rejected | reason: no exact authoritative image/geolocation tool matching this name and contract was verified."
paid_status: unverified
~~~

The exact upstream, license, invocation, pricing, and current maintenance date remain unknown.

### geospy

~~~yaml
name: geospy
input_types: [image]
invocation: api
requires_key: true
legal_tier: 2  # proposed; not accepted
license: "Hosted proprietary service"
verification_status: proposed-unverified
verification: "rejected | reason: the official product page says GeoSpy is now Raven; no verified free API path matching the proposal was found."
paid_status: paid-only
~~~

Official source: https://graylark.com/geospy. Product identity has changed and the identified service/API path is not a verified free integration.

### picarta

~~~yaml
name: picarta
input_types: [image]
invocation: api
requires_key: true
legal_tier: 2  # proposed; not accepted
license: "Hosted proprietary service"
verification_status: proposed-unverified
verification: "rejected | reason: official API documentation limits API access to Enterprise accounts; a free website tier does not make the API integration free."
paid_status: paid-only
~~~

Official sources: https://docs.picarta.ai/ and https://picarta.ai/terms-conditions.
