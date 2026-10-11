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

## Pending review

**LeakCheck** remains pending review and is not integrated. Its proposed provenance is through OSINT-Hub, described as a Discord-based breach-data aggregator. Before any implementation, confirm the source's provenance and response fields; reject any path that yields plaintext credentials, stolen tokens, or criminal-market content. The proposed password-hash input is not approved for current use.

## Future re-addition

The three removed integrations are absent from the current default registry. Any proposal to re-add one requires a new review of current pricing, terms, secrets handling, license, and default behavior. This note does not authorize an implementation.
