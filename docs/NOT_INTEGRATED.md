# Not Integrated

This page records tools excluded from the current registry and proposals that need review. It does not claim that a tool was installed, executed, or tested by Aletheia.

## Excluded at the hard floor: criminal provenance or secret exposure

These exclusions are project-policy classifications supplied for this direction; this task did not independently inspect or execute these products.

- **LeakRadar:** described as exposing plaintext credentials from stealer logs and combolists and indexing dark-web forum/marketplace posts.
- **OsintCat:** described as aggregating breach-data providers, with Discord lookup that may return tokens or passwords.
- **OathNet:** described as combining breach databases, stealer logs, and Discord user data including tokens.

The boundary is source and output provenance: grey allows public data with unclear terms when no plaintext secrets or criminal-market content are collected; criminal-provenance material remains excluded. A future adapter must not ingest plaintext credentials, stolen session tokens, or marketplace content.

## Removed integrations

Twilio Lookup, Censys, and Google Cloud Vision were removed from the current adapter registry and Docker verification set by project decision. The earlier description of all three as “paid-only” was not accurate against current official pricing:

- **Twilio Lookup:** the Basic formatting and validation operation used by the removed integration is currently listed as free. Additional carrier, identity, and risk features can be billed per request. The integration is removed by project policy; the basic endpoint is not described here as paid-only. [Twilio Lookup pricing](https://www.twilio.com/en-us/user-authentication-identity/pricing/lookup)
- **Censys:** Free accounts currently receive 100 credits per month. The documented entity lookup costs 1 credit and a standard query costs 5 credits, so the free quota is limited but real. The integration is removed by project decision about quota fit, not because Censys has no free access. [Censys credits for Free and Starter users](https://docs.censys.com/docs/platform-credits-free-starter)
- **Google Cloud Vision:** each feature currently has its own first 1,000 units per month free, after which feature-specific charges apply. The integration is removed by project decision about the limited quota and potential spend, not because every use is paid-only. [Cloud Vision pricing](https://cloud.google.com/vision/pricing)

The current source tree no longer contains these adapters, their Docker images/build targets, parser or integration cases, capture cases, manifest entries, or target-specific adapter notes. Old audit logs and changelog entries remain historical records of the earlier checkpoint.

## Retained API integrations and key-cost corrections

The project direction explicitly retains Shodan, HIBP, Reddit API, YouTube Data API, and OpenCorporates. Requiring a key does not mean the use is free:

- **Shodan:** a free-account API key is available, subject to account plan and terms. [Shodan API requirements](https://developer.shodan.io/api/requirements)
- **HIBP:** a subscription is required for direct email-account API lookups; the separate Pwned Passwords API is not the same endpoint. It is retained per project direction, but must not be labeled free. [HIBP subscription plans](https://haveibeenpwned.com/subscription) · [HIBP API v3](https://haveibeenpwned.com/API/V3)
- **Reddit API:** OAuth access and use are subject to current developer terms and quotas; Reddit reserves the right to charge and requires a separate agreement for commercial or otherwise unauthorized use. Do not encode a universal “free” guarantee. [Reddit Data API Terms](https://redditinc.com/policies/data-api-terms)
- **YouTube Data API:** projects have a default quota allocation, currently 10,000 units per day for most read endpoints, subject to quota, project, and terms requirements. [YouTube Data API quota guidance](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- **OpenCorporates:** default limits are currently documented as 200 requests per month and 50 per day. API accounts are free for qualifying open-data projects under share-alike and attribution terms; other access may require a paid account. Aletheia has not verified that its own distribution satisfies those license conditions. [OpenCorporates API reference](https://api.opencorporates.com/documentation/API-Reference)

Current manifest legal notes must state the actual key-cost conditions. In particular, the requested blanket free-cost label for HIBP is not used because it would be false for direct email lookups.

## Excluded and pending proposals

**LeakCheck** is excluded from Phase 5b by the project owner (2026-10-11). It is not integrated. No source was queried and no implementation was attempted. The previous registry proposal's provenance and output behavior were not independently verified.

### Phase 5b exclusions after scoped source review (2026-10-11)

These proposals were reviewed against the project owner's requirement to verify a stable invocation that can be constrained to Tier 1–2 content. The documented call paths did not meet that condition, so they were moved out of the active proposal registry. No adapter was installed or run.

~~~yaml
name: hudsonrock
status: excluded
scope_constraint: "No stable, documented Boolean-only infection-signal API was found. The official API requires an API key; its username route searches compromised credentials, and documented domain/stealer responses include credential objects with username and password fields. Aletheia must not call those endpoints."
evidence:
  - https://docs.hudsonrock.com/reference/authentication
  - https://docs.hudsonrock.com/docs/username-search
  - https://docs.hudsonrock.com/docs/domain-search
~~~

~~~yaml
name: darknyx
status: excluded
scope_constraint: "No public metadata-only entity-search API or exact public API endpoint is documented. The free web search covers onion sites, leak dumps, and marketplaces; its legal notice says personal-data masking is incomplete and prohibits scraping. API access is a Pro feature. Aletheia cannot verify a Tier 1–2-only response boundary or use the public page as an undocumented scraper."
evidence:
  - https://darknyx.com/
  - https://darknyx.com/legal/
~~~

~~~yaml
name: osint-darkweb-pkg
status: excluded
scope_constraint: "The published get_search_results(query) call concurrently queries 17 hardcoded .onion search endpoints, not only Ahmia, Torch, and OnionLand, and returns titles and onion URLs without engine provenance or a supported engine allowlist. A separate scrape_multiple(urls) call fetches onion pages and extracts up to 1200 characters; Aletheia would not call it, and page fetching is not required by the search function itself. The package offers no documented way to restrict its public invocation to the three approved engines. At least its hardcoded Torch endpoint differs from the current address published by Torch's own site, so endpoint ownership/current status cannot be trusted from the package source alone."
evidence:
  - https://pypi.org/project/osint-darkweb-pkg/
  - https://files.pythonhosted.org/packages/source/o/osint-darkweb-pkg/osint_darkweb_pkg-0.1.0.tar.gz (SHA-256: 7a42152d02d3493ec01e8913964e05b4b850107f9be06f50ba89978795463e42; statically inspected; not installed or executed)
  - https://torch.cx/about/ (current canonical onion address published by Torch)
~~~

## Future re-addition

The three removed integrations are absent from the current default registry. Any proposal to re-add one requires a new review of current pricing, terms, secrets handling, license, and default behavior. This note does not authorize an implementation.
