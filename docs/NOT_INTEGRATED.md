# Not Integrated

This page records tools not currently integrated and source-review history. A status of “allowed” under the Florida project policy does not mean that a tool was installed, implemented, executed, or verified by Aletheia.

## Previously excluded — now allowed under Florida framework

The project owner changed the project policy on 2026-10-12. These sources are no longer excluded by the project-level Tier 5 classification; each remains unimplemented and unverified unless stated otherwise elsewhere.

- **LeakCheck:** allowed, including the free OSINT-Hub path. No source was queried or implementation attempted during this review.
- **LeakRadar:** allowed by project policy; previously described as a stealer-log/combolist and dark-web index.
- **OsintCat:** allowed by project policy; previously described as an aggregator that may return tokens or passwords.
- **OathNet:** allowed by project policy; previously described as combining breach databases, stealer logs, and Discord user data.
- **Blackbird:** allowed by project policy. Earlier source review found no declared upstream license and described optional HTML/AI features; these remain integration/licensing facts to resolve before bundling, not a policy exclusion.
- **Lullar:** allowed by project policy. Earlier source review found a browser URL-generation workflow and no documented machine-readable interface; this remains an implementation limitation, not a policy exclusion.
- **Hudson Rock:** allowed by project policy, including the documented username endpoint that may return credential fields. No Aletheia adapter or endpoint call was added. Any future credential parsing/storage must remain structurally separate from authenticated HTTP code.

This section records Aletheia policy only. It is not a legal conclusion, a claim that these sources are accurate or licensed for every use, or evidence of an integration. ONYPHE remains excluded for its own-systems Free View scope mismatch, as recorded below. Other source-specific Phase 5c exclusions remain unchanged.

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

## Integration reviews and pending proposals

### Phase 5b historical review notes (2026-10-11)

The following source facts were documented when these proposals were excluded under the prior project posture. The owner later changed the project policy so the sources listed in the Florida section above are allowed; the facts remain useful for implementation planning, but are no longer Tier 5 exclusions:

- Hudson Rock's official username endpoint is `POST https://api.hudsonrock.com/json/v3/search-by-login/usernames`; its documented response contains stealer/device fields and `credentials[]` username/password fields. Earlier review found no stable Boolean-only infection-signal endpoint. Sources: https://docs.hudsonrock.com/docs/username-search and https://docs.hudsonrock.com/docs/domain-search.
- DarkNyx's public site describes indexing onion sites, leak dumps, ransomware groups, public Telegram, and marketplaces; its homepage describes API access as Pro and its legal terms prohibit scraping. Earlier review found no documented public metadata-only API. Sources: https://darknyx.com/ and https://darknyx.com/legal/.
- `osint-darkweb-pkg`'s `get_search_results(query)` was statically inspected and found to query 17 hardcoded onion endpoints; a separate `scrape_multiple(urls)` fetches pages. Earlier review found no public engine allowlist. The package was not installed or executed. The inspected archive SHA-256 was `7a42152d02d3493ec01e8913964e05b4b850107f9be06f50ba89978795463e42`.
- Blackbird's current repository is https://github.com/antoniaci/blackbird. Earlier review found no declared license and optional HTML/AI output flags; source references: https://github.com/antoniaci/blackbird and https://github.com/antoniaci/blackbird/blob/main/blackbird.py.
- Lullar's checker page documents browser URL generation and manual review; earlier review found no documented CLI or machine API. Sources: https://com.lullar.com/en/tools/username-checker and https://com.lullar.com/en/guide/social-media-username-search.

### Phase 5c exclusions after source and scope review (2026-10-11)

- **ONYPHE:** excluded by owner decision. The official Free & Web View terms limit the free license to individual use, prohibit commercial reuse, and distinguish paid use for professional/client purposes. No Aletheia integration was added.
- **Mr.Holmes:** the single upstream tool combines broad lookups with Google dorks, proxy support, and an interactive startup. No supported bounded invocation that excludes those behaviors was verified.
- **IVRE:** a self-hosted data/recon platform whose useful query results require populated databases and whose active integrations include multiple scanners. It is not a bounded seed lookup without backend and scanning scope expansion.
- **urlscan:** excluded because its current terms limit use to personal use and restrict commercial endeavors; Aletheia cannot enforce that boundary for every operator/deployment. No scans were submitted.
- **ThreatCluster:** the free key includes dark-web search/read endpoints and leak-site victim-enrichment routes; no endpoint/schema pair was verified that guarantees a Tier 1–2-only result for Aletheia's general use. Its free plan is also described for personal/evaluation use.
- **Social Analyzer:** its broad multi-site workflow spans more than 1,000 social websites and uses multiple request/metadata techniques; no per-site allowlist and rate/terms scope was established.

The Phase 5c proposals **Gravatar** and **RDAP** are narrowly scoped integrations: Gravatar uses the official profile API with the email SHA-256 hash and a curated public-field allowlist; RDAP uses IANA bootstrap data for one exact domain/IP lookup. RDAP is `verified-fixture` based on Docker Verification run 38270478612 (synthetic fixture, parser coverage, image build, and offline health smoke only); no live RDAP lookup occurred. See `PROJECT_MANIFEST.json` and `docs/PHASE_5C_REGISTRY.md` for status and scope.

## Future re-addition

The three removed integrations are absent from the current default registry. Any proposal to re-add one requires a new review of current pricing, terms, secrets handling, license, and default behavior. This note does not authorize an implementation.
