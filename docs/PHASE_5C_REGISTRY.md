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

## Phase 5c scope decisions (2026-10-11)

The following two proposals have a narrow, documented public-data path suitable for implementation. This decision does not imply that their adapters are built or verified; their manifest status remains `unknown` until code, fixtures, and CI evidence exist.

### gravatar — scoped for implementation

`GET https://api.gravatar.com/v3/profiles/{identifier}` accepts the SHA-256 hash of the normalized email address; the API documents the bearer token as optional and notes that profile lookup resolves only the account's primary address. The wrapper scope is limited to one exact email hash and a curated set of public profile fields. It must not transmit the email itself, infer identity from a profile match, or emit fields such as email addresses or phone numbers. The provider says profile data is accessible through its public API; its privacy guidance also says profile-page visibility controls are not API privacy controls, so operator authorization and a caution in the adapter notes remain required.

Sources: https://docs.gravatar.com/sdk/profiles/ ; https://support.gravatar.com/your-profile/visibility-settings/ ; https://support.gravatar.com/privacy-and-security/profile-access/.

### rdap — scoped for implementation

Use only the standard RDAP bootstrap registries published by IANA, then issue one exact `/domain/{domain}` or `/ip/{address}` registration-data lookup to the selected registry. The implementation must not probe the target, enumerate related names or addresses, or query data outside the seed. This is a standards-based lookup rather than a bundled third-party client; use the Python standard library and preserve the registry/record URL as provenance.

Sources: https://www.iana.org/assignments/rdap-dns ; https://data.iana.org/rdap/ipv4.json ; https://data.iana.org/rdap/ipv6.json ; https://www.rfc-editor.org/rfc/rfc9224.html ; https://www.rfc-editor.org/rfc/rfc9082.html.

## Phase 5c exclusions after scope review (2026-10-11)

### mr-holmes — excluded

The upstream describes one broad collection tool that combines public-source lookups with Google dorks and proxy support, and its documented startup is interactive. There is no verified supported invocation that cleanly disables the dorking/proxy features and produces a bounded, machine-readable result for one Aletheia seed. Aletheia will not bundle or invoke the broad tool speculatively.

Source: https://github.com/Lucksi/Mr.Holmes.

### onyphe — excluded by owner decision

The official Free & Web View terms say the free individual license has no commercial reuse right and describe use of output for the customer's own account; the terms also distinguish paid business use for a customer's clients. The owner chose to exclude ONYPHE rather than embed a key-dependent service whose documented free-use boundary does not match Aletheia's general target workflow.

Sources: https://search.onyphe.io/files/cgus-v6.41.pdf ; https://search.onyphe.io/files/onyphecheatsheetfreeview.pdf.

### ivre — excluded

IVRE is a self-hosted network-reconnaissance framework and data platform. Its documented active-recon integrations include Nmap, Masscan, ZGrab2, ZDNS, Nuclei, httpx, dnsx, tlsx, and Dismap; the passive data path ingests operator network sensors. It does not provide a single bounded passive lookup API for a seed without first deploying and populating its data platform. Wrapping it here would either return no useful lookup data or expand scope into active scanning and backend deployment.

Sources: https://github.com/ivre/ivre ; https://github.com/ivre/ivre/blob/master/doc/usage/active-recon.rst ; https://github.com/ivre/ivre/blob/master/doc/overview/principles.rst.

### urlscan — excluded

The API can search existing scans, but urlscan's current terms limit use of the service and its content to personal use and restrict commercial endeavors. This project cannot enforce that restriction for every operator or deployment. The adapter is therefore excluded rather than making the source a default capability. No scans were submitted.

Sources: https://urlscan.io/docs/api/ ; https://urlscan.io/docs/search/ ; https://urlscan.io/terms/.

### threatcluster — excluded

The free key includes read access to dark-web endpoints, unified search that can search the dark web, and victim-enrichment routes that expose leak-site material. The published free plan is for evaluation and personal use, while commercial use and product embedding have separate terms. No documented endpoint-and-schema combination was verified that both fits Aletheia's general use and guarantees exclusion of criminal-provenance content, so this candidate is excluded.

Sources: https://threatcluster.io/pricing ; https://threatcluster.io/about/free-api ; https://threatcluster.io/api/public/v1/docs.

### social-analyzer — excluded

The upstream advertises profile search across more than 1,000 social websites and combines HTTP and WebDriver techniques, metadata extraction, search-engine lookups, and other modules. No maintained, source-specific allowlist with per-site permissions and rate controls was established for a legally bounded Aletheia wrapper. A broad multi-site automation integration is not added.

Sources: https://github.com/qeeqbox/social-analyzer ; https://github.com/qeeqbox/social-analyzer/blob/main/app.py.

The previously rejected proposals remain rejected for the reasons recorded above. Phase 5c has no inferred twentieth proposal. Only Gravatar and RDAP proceed to implementation; urlscan, ONYPHE, IVRE, ThreatCluster, Mr.Holmes, and Social Analyzer are excluded.
