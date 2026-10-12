# Aletheia Project Direction

> Strategy record only. This document does not change the current CLI, router, adapter enforcement, or live investigation behavior. The Florida project posture supersedes the older grey posture and tier ladder below; the repository still uses its existing legal-only and authorization-assertion implementation.

## Purpose

Aletheia's project policy is based on Florida, USA. It does not use the earlier court-defensibility-first or generic grey posture. The four prohibited categories below are the project's Tier 5 floor; they are not an exhaustive summary of Florida or federal law. Every operation remains subject to applicable law, court orders, source access controls, and any binding service terms. This document is a project policy record, not legal advice or a determination that a particular collection method is lawful.

Under the project policy, public automation, leak indexes, aggregators, stealer-log indexes, dark-web search indexes, operator-owned account workflows, bulk processing, and plaintext credential storage may be considered for integration, subject to the explicit structural rule below and separate implementation review. A source being permitted by project policy does not mean it is implemented, verified, or suitable for every target.

## The three modes — all always on

There is no mode selector in the target operator experience; the current CLI retains its existing legal-only interface. The three mode names below describe future behaviors that run together on every investigation:

1. **Open behavior:** dispatch every matching Tier 1 source without a separate gate.
2. **Personal behavior:** record an optional declaration of lawful basis in the audit trail. An empty declaration does not stop a run.
3. **Sensitive behavior:** produce the full audit trail and evaluate jurisdiction-warning conditions. A warning is informational, not a dispatch gate.

The jurisdiction warning should activate when the seed or a finding indicates a strong-privacy jurisdiction, a minor, health data, or a protected-class context. This is a future requirement; this document does not claim that the current implementation performs those checks.

## Max power by default

Every adapter that matches the seed and has its prerequisites met is intended to run by default. Missing-key cases are recorded as skips with their reason. There are no opt-in switches, per-adapter enable toggles, or mode-based dispatch gates in the target model.

Every manifest adapter is intended to carry:

- legal_tier: integer from 1 through 5
- enabled_by_default: boolean
- disabled_reason: string or null; required when enabled_by_default is false
- batch_grouping: string or null

The Phase 5b/5c registries are proposals only. Their entries do not mean that code, routing, credentials, or runtime enforcement already exists. Sources newly permitted by the Florida policy remain unimplemented unless they have a separate integration entry and implementation.

## Tier ladder and hard floor

| Tier | Category | Project default |
| --- | --- | --- |
| 1 | Public, unauthenticated, no ToS concern | On |
| 2 | Public, ToS-hostile to automation | On |
| 3 | Requires a free API key | On when the key is present |
| 4 | Leak indexes, aggregators, plaintext credential sources, dark-web indexes, stealer logs | On |
| 5 | Unauthorized computer access; communications interception; criminal marketplace transactions; stalking/harassment | Off |

The project's hard floor prohibits Tier 5 activities: unauthorized computer access (including use of another person's credentials or bypassing CAPTCHAs/paywalls), communications interception, criminal marketplace transactions, and stalking or harassment. Tier metadata and defaults are project policy; the current runtime loader has no constructor-time tier enforcement. This table does not override other laws, court orders, contractual limits, or source-specific access controls.

## Posture shift note — Phase 5b

Phase 5b adds a proposed breadth wave of username, email, phone, and public-source checks. The registry records scope and current verification gaps. The Florida project policy now permits LeakCheck, LeakRadar, OsintCat, OathNet, Hudson Rock, Blackbird, and Lullar; permission is not implementation or verification. ONYPHE remains excluded because its Free View terms restrict use to the operator's own systems. Other Phase 5b/5c exclusions remain as recorded unless a later reviewed decision changes them.

### Structural safeguard

Code that parses and stores credential values must live in a different module and use a different interface from code that makes authenticated HTTP requests. Those paths must not share an HTTP client that could be redirected to a login endpoint. This is a code-level separation requirement; it does not approve credential use against accounts or services.

## Batch grouping table

Group membership is a planning aid for later consolidated adapters. It does not imply that the listed tools are integrated, approved for every use, or verified live. A tool may belong to more than one logical group; the manifest field carries one primary grouping.

| Batch | Members and status | Tier / notes |
| --- | --- | --- |
| breach_search | HIBP (current); XposedOrNot (implemented); LeakCheck, LeakRadar, OsintCat, OathNet, and Hudson Rock (permitted, not integrated) | Mixed Tier 2–4; HIBP direct email-account lookups require a paid subscription |
| stealer_log | Hudson Rock, LeakRadar (permitted, not integrated) | Tier 4 project policy; any implementation requires the structural safeguard and separate review |
| darkweb_search | Ahmia, Torch, OnionLand, DarkSearch, DarkNyx, osint-darkweb-pkg (permitted, not integrated); ThreatCluster (excluded); Vamp Darkweb Intel (rejected) | Mixed Tier 2–4; see `NOT_INTEGRATED.md` for unresolved integration issues |
| username_enum | Sherlock, Maigret (current); Blackbird (permitted, not integrated); Nexus OSINT (rejected) | Tier 2 |
| phone_intel | PhoneInfoga, libphonenumber (current) | Tier 1 |
| people_search | Lullar (permitted, not integrated); Mr.Holmes (excluded after source review); OSINT Search Tool (rejected) | Tier 2; constrain to public-source policy and target scope |
| email_intel | Gravatar (implemented); GHunt (permitted, not integrated); EmailRep (rejected) | Mixed Tier 1–3; GHunt may use only the operator's own account |
| domain_intel | theHarvester, Amass, Subfinder, Assetfinder (current); RDAP (implemented; verified-fixture in Docker Verification run 38270478612); ONYPHE, IVRE, and urlscan.io (excluded after source review) | Mixed Tier 1/2 |
| social_media | Instaloader, Reddit API, YouTube API (current); Social Analyzer (excluded after source review); Twint fork and Osintgram (rejected) | Tier 2 for public-profile automation; no login or bypass |
| geoint | DeepGround, GeoSpy, Picarta (rejected or paid/identity unclear) | Tier 2 proposals; no implementation approved |
| threat_intel | Shodan (current); ONYPHE and ThreatCluster (excluded after source review) | Mixed Tier 2/3 |
| dns_records | DNSX, MassDNS, DNSRecon, Fierce (current) | Tier 1/2; wrapper scope and applicable law still matter |
| certificate_transparency | crt.sh (current) | Tier 1 |
| company_registry | SEC EDGAR, GLEIF, OpenCorporates (current) | Mixed Tier 1/3 |
| sanctions_multi | OpenSanctions (current) | Tier 3 |
| geoint_local | ExifTool, DeepFace, InsightFace, Overpass, SunCalc (current) | Tier 1; local/image analysis stays limited to its documented scope |

Phase 9 remains a separate future planning list: dns_records, certificate_transparency, threat_intel, ip_geolocation, whois_multi, paste_search, code_search, sanctions_multi, company_registry, archive_lookup, search_engines, academic_search, news_search, vehicle_vin, flight_tracking, maritime_ais, historical_weather, and social_public_json.

## Deliverables when implemented

- Manifest metadata for every adapter and construction-time rejection of Tier 5; Tier 4 remains enabled under the project policy subject to applicable law and source constraints.
- Router behavior that dispatches matching Tier 1/2 adapters unconditionally and records missing Tier 3 keys as skips.
- Optional lawful-basis declaration recording, without blocking the run when it is empty.
- Informational jurisdiction warnings and a full audit trail on every run.
- Reports that list adapters run, skipped, and the reason for each skip.
- Tier, source, license, rate-limit, grouping, and verification metadata maintained with each adapter.

## What this is not

- Not an implementation task or a statement that the current CLI supports the target behavior.
- Not legal advice, a complete statement of Florida/federal law, or a guarantee that a specific collection method is lawful.
- Not permission to access an account without authorization, intercept communications, transact in criminal marketplaces, or engage in stalking/harassment.
- Not a change to the requirement that credential parsing/storage remain structurally separate from authenticated HTTP code.
- Not a change to storage, egress control, audit integrity, or verification claims.
- Not authorization to implement the proposed Phase 5b or Phase 5c tools without their own scoped review.

## Phase 5c source-check snapshot

The proposed list supplied with this direction names 19 tools although it calls the list 20. No twentieth tool has been inferred. Primary-source checks and outcomes are recorded in [PHASE_5C_REGISTRY.md](PHASE_5C_REGISTRY.md). A source check verifies public documentation or repository facts; it does not verify a future Aletheia adapter or a live tool run.

## Roadmap — Future Features

### Multi-seed investigations (Phase 9+)

Aletheia should eventually accept multiple seeds — e.g. two usernames — plus
optional context filters (country, age range, language, timezone). The router
expands each seed as an independent tree; the resolver runs an intersection
pass; entities appearing in multiple trees get a confidence boost; constraint
filters apply at every layer.

Expected accuracy improvement on multi-seed investigations: ~88% precision /
65% recall → ~93% / 80%. Estimated effort: 2–4 sessions.

Not part of Phase 8. Do not implement until the current phase pipeline is complete.
