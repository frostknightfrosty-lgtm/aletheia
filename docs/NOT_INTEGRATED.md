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

## Phase 9 batch-plan source re-verification (2026-10-15)

### FollowTheMoney / OpenSecrets — not integrated, adapter NOT built

`docs/BATCHING_PLAN.md` listed a `corporate_financial_public_records` composite containing a
"FollowTheMoney API" sub-source, described as "Tier 3 / Free API Key". Re-verification against the
vendors' own documentation on 2026-10-15 found that premise is outdated on both readings, so
**no adapter, runner, image, fixture, test, or manifest entry was created.**

**1. OpenSecrets' public API was discontinued.** OpenSecrets' own API page states, verbatim:
*"As of April 15, 2025, our API offerings have been discontinued."* The only remaining route it
offers is a commercial arrangement (*"Reach out to commercial@opensecrets.org"*), which is
paid-only and therefore barred by standing rule 4 ("Do not add paid-only adapters") and Gate 3.
Source: https://www.opensecrets.org/open-data/api

**2. FollowTheMoney's name-query request contract is not published.** FollowTheMoney (National
Institute on Money in State Politics) merged into OpenSecrets; its site is explicitly
unmaintained — *"This website displays state campaign finance data that is current through the
2024 election year. While the data is current, the site isn't maintained as we integrate with
OpenSecrets and you may find bugs."* What its official documentation does and does not contain:

- **Verified:** base URL `https://api.followthemoney.org/` (live; returns `invalid mode` with no
  `mode`); `APIKey` is the auth query parameter, obtained free with a myFollowTheMoney account
  (*"The Institute's APIs are immediately available for use after you create a free myFollowTheMoney
  account"*, *"The Institute grants you free access"*); `mode=json` is valid — an unauthenticated
  probe returns exactly `{"error":"Invalid API Key"}`; the JSON response schema is
  `{"metaInfo": {...}, "records": [...]}`.
- **The only concrete documented request example** is the Entity Details API, keyed by a numeric
  entity ID rather than a name:
  `http://api.followthemoney.org/entity.php?eid=#######&APIKey=XXXXXXXX&mode=xml`
- **Not published:** the request-parameter set for name-based ("Ask Anything") queries. The
  official 80-page API PDF (`https://www.followthemoney.org/assets/FollowTheMoney-API.pdf`,
  extracted and searched in full) contains **zero** occurrences of `api.followthemoney.org`,
  `APIKey`, `mode=`, or `entity.php` — it documents the *response* tags only. The official
  documentation instructs operators to build the query in the website UI and copy the generated
  export link.
- **Not published:** any rate limit. No numeric quota appears on the API page, the Documentation
  page, the Support/FAQ page, or the PDF.

Writing a name-search runner would therefore require inventing request parameters, which the
no-fabrication rule forbids. The sub-source is **not implemented**. This is a documentation and
availability finding, not a Tier 5 or licensing objection.

Sources: https://followthemoney.org/our-data/apis/ ·
https://followthemoney.org/our-data/apis/documentation/ ·
https://followthemoney.org/our-data/apis/support/ ·
https://www.followthemoney.org/assets/FollowTheMoney-API.pdf ·
https://www.opensecrets.org/open-data/api

Verification commands and raw output:

```
$ curl -s "https://api.followthemoney.org/?mode=json"
{"error":"Invalid API Key"}
$ curl -s "https://api.followthemoney.org/"      # no mode parameter
invalid mode
$ python -c "from pypdf import PdfReader; t=''.join(p.extract_text() or '' for p in PdfReader('FollowTheMoney-API.pdf').pages); print(len(t), [t.count(s) for s in ['api.followthemoney.org','APIKey','mode=','entity.php']])"
95679 [0, 0, 0, 0]
```

## P17.13 horizon exclusions (2026-10-20)

These are written exclusions, not silent omissions. None is owner-gated; each was
reviewed and rejected or recorded as already covered.

- **NameMC** — no public API is documented, and its site terms do not authorize
  scraping. The free Mojang current-profile API is implemented as `minecraft`;
  NameMC name history is deliberately not fetched, so only the current handle is
  reported. Re-adding would require a licensed API or explicit permission.
- **Social-graph list ingestion** — the horizon item is already covered in
  substance by the pinned maigret/sherlock site enumeration used by
  `social_username`; a second list adapter would duplicate the same public site
  metadata without adding a source. No new adapter is justified.
- **news_search** — GDELT's DOC endpoint rejects the descriptive `Aletheia/0.1`
  User-Agent with its rate-limit message even after waiting, so it is not a
  usable contract under the no-workaround rule. Public Google News and Bing News
  RSS endpoints are reachable, but neither documents an automated-search API or
  grants that permission in its terms; keyed news APIs are Gate 3 owner
  registrations. The item is parked with this reason, not implemented by
  impersonating another User-Agent or scraping a news page.

## Future re-addition

The three removed integrations are absent from the current default registry. Any proposal to re-add one requires a new review of current pricing, terms, secrets handling, license, and default behavior. This note does not authorize an implementation.
