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

These proposals were reviewed against the project owner's requirement to verify a stable invocation that can be constrained to Tier 1–2 content. The documented call paths did not meet that condition, so they were moved out of the active proposal registry. No adapter was installed or run. The owner's exact review conditions were applied: if a source lacks a documented, enforceable safe scope, it is excluded rather than implemented speculatively.

~~~yaml
name: hudsonrock
status: excluded
scope_constraint: "The official username endpoint is POST https://api.hudsonrock.com/json/v3/search-by-login/usernames and requires the search-by-login API permission. Its documented response contains stealer/device fields and credentials[] with username and password fields. No stable Boolean-only infection-signal endpoint was documented. Exclude; do not call the credential-returning route."
evidence:
  - https://docs.hudsonrock.com/docs/username-search
  - https://docs.hudsonrock.com/docs/domain-search
~~~

~~~yaml
name: darknyx
status: excluded
scope_constraint: "The public site search is described as indexing onion sites, leak dumps, ransomware groups, public Telegram, and marketplaces. The homepage identifies API access as a Pro feature, and the legal terms prohibit scraping, probing, or bypassing service filters. No documented public entity-search API returning only category, snippet, onion URL, or a sanitized feed was found. Exclude; do not scrape the public page or use paid Pro API access."
evidence:
  - https://darknyx.com/
  - https://darknyx.com/legal/
~~~

~~~yaml
name: osint-darkweb-pkg
status: excluded
scope_constraint: "The documented get_search_results(query) sub-call queries 17 hardcoded .onion search endpoints, not only Ahmia, Torch, and OnionLand, and returns titles/links without engine provenance or an engine allowlist. It cannot be constrained to the three approved indexes through its public interface. The separate scrape_multiple(urls) sub-call fetches .onion pages and extracts page text; Aletheia would not call it. The search sub-call itself does not require page fetching, but its engine set and provenance fail the owner's scope condition. Exclude this package; do not invoke scrape_multiple or substitute an undocumented patched call path."
evidence:
  - https://pypi.org/project/osint-darkweb-pkg/
  - https://files.pythonhosted.org/packages/source/o/osint-darkweb-pkg/osint_darkweb_pkg-0.1.0.tar.gz (SHA-256: 7a42152d02d3493ec01e8913964e05b4b850107f9be06f50ba89978795463e42; statically inspected; not installed or executed)
  - https://torch.cx/about/ (current canonical onion address published by Torch)
~~~

~~~yaml
name: blackbird
status: excluded
scope_constraint: "The current official repository is https://github.com/antoniaci/blackbird (the former p1ngul1n0 URL redirects there). The documented username CLI is python blackbird.py --username <username>; optional flags can dump HTML or send found site names to an external AI service. The repository has no declared license (GitHub API license field is null and the repository root has no LICENSE file), so Aletheia cannot legally redistribute or bundle it. The repository's latest push was 2025-07-13; maintenance freshness is also unestablished. Exclude unless the upstream publishes a license and supported, scopeable invocation."
evidence:
  - https://github.com/antoniaci/blackbird
  - https://github.com/antoniaci/blackbird/blob/main/blackbird.py
~~~

~~~yaml
name: lullar
status: excluded
scope_constraint: "The current public username-checker page documents URL generation in the browser: it creates profile URLs and the visitor opens a profile to decide whether it loads or returns 404. No CLI, machine-readable API, source repository, or automation license was documented. The marketing page's claims of automatic parallel checking conflict with the dedicated checker instructions. Exclude; do not scrape the site or automate checks across third-party platforms without a documented interface and scope."
evidence:
  - https://com.lullar.com/en/tools/username-checker
  - https://com.lullar.com/en/guide/social-media-username-search
~~~

## Future re-addition

The three removed integrations are absent from the current default registry. Any proposal to re-add one requires a new review of current pricing, terms, secrets handling, license, and default behavior. This note does not authorize an implementation.
