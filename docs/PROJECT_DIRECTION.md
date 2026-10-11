# Aletheia Project Direction

> Strategy record only. This document does not change the current CLI, router, adapter enforcement, or live investigation behavior. Where older direction notes conflict, this newer accepted direction is authoritative. The repository still uses the existing legal-only and authorization-assertion implementation. The three-mode model below is the target for later work.

## Purpose

Aletheia is shifting from a court-defensibility-first posture to a grey posture similar to SpiderFoot: public sources with unclear or automation-hostile terms may be used, while the hard floor remains unchanged. The project may accept public-data collection where terms are unclear, subject to jurisdiction warnings and the operator's lawful basis.

Grey does not include plaintext credentials, stolen session tokens, leaked databases, criminal marketplace material, authentication bypass, or private data. Those remain excluded.

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

The Phase 5b/5c registries are proposals only. Their entries do not mean that code, routing, credentials, or runtime enforcement already exists. LeakCheck was excluded by the project owner on 2026-10-11 and is not a Phase 5b implementation target.

## Tier ladder and hard floor

| Tier | Description | Target dispatch rule |
| --- | --- | --- |
| 1 | Public, unauthenticated, no material terms-of-service concern | Dispatch unconditionally |
| 2 | Public, but terms may be hostile to automation | Dispatch unconditionally; record jurisdiction warning where relevant |
| 3 | Requires an API key used in terms-compliant ways | Dispatch when the key is present; otherwise record a missing-key skip |
| 4 | Requires consent or warrant, including logged-in/private data or intercepted communications | Hard floor: do not register |
| 5 | Authentication bypass, leaked databases, plaintext secrets, stolen tokens, or criminal provenance | Hard floor: do not register |

Tier 4 and Tier 5 are permanently excluded from the registry. The desired adapter interface must reject those tiers at construction time. This task records tier metadata in the manifest, but the current runtime loader has no constructor-time enforcement for it; this remains a future requirement, not a verified current safeguard.

## Posture shift note — Phase 5b

Phase 5b adds a proposed breadth wave of username, email, phone, and public-source checks. The registry records scope and current verification gaps. It is not permission to install or run those tools. LeakCheck is excluded, and proposed tools that expose credentials, require target login, or cross the hard floor must not be implemented as written.

## Batch grouping table

Group membership is a planning aid for later consolidated adapters. It does not imply that the listed tools are integrated, approved for every use, or verified live. A tool may belong to more than one logical group; the manifest field carries one primary grouping.

| Batch | Members and status | Tier / notes |
| --- | --- | --- |
| breach_search | HIBP (current); XposedOrNot (proposed); Hudson Rock (proposed); LeakCheck (excluded) | Mixed Tier 1/3; HIBP requires a paid subscription for direct email-account lookups |
| stealer_log | Hudson Rock (proposed) | Tier 1 proposal; return infection signals only, never plaintext |
| darkweb_search | osint-darkweb-pkg, Darknyx (proposed); ThreatCluster (source-verified proposal); Vamp Darkweb Intel (rejected) | Mixed Tier 1/2 proposals; exclude credential and criminal-market content |
| username_enum | Sherlock, Maigret (current); Blackbird (proposed); Nexus OSINT (rejected) | Tier 2 |
| phone_intel | PhoneInfoga, libphonenumber (current) | Tier 1 |
| people_search | Lullar (proposed); Mr.Holmes (source-verified proposal); OSINT Search Tool (rejected) | Tier 2; constrain to unauthenticated public sources |
| email_intel | Gravatar (source-verified proposal); GHunt and EmailRep (rejected) | Mixed Tier 1/2; GHunt requires account cookies, EmailRep does not issue new keys |
| domain_intel | theHarvester, Amass, Subfinder, Assetfinder (current); ONYPHE, IVRE, urlscan.io, RDAP (source-verified proposals) | Mixed Tier 1/2 |
| social_media | Instaloader, Reddit API, YouTube API (current); Social Analyzer (source-verified proposal); Twint fork and Osintgram (rejected) | Tier 2 for public-profile automation; no login or bypass |
| geoint | DeepGround, GeoSpy, Picarta (rejected or paid/identity unclear) | Tier 2 proposals; no implementation approved |
| threat_intel | Shodan (current); ONYPHE and ThreatCluster (source-verified proposals) | Mixed Tier 2/3; ThreatCluster requires source/field screening |
| dns_records | DNSX, MassDNS, DNSRecon, Fierce (current) | Tier 1/2; wrapper scope and applicable law still matter |
| certificate_transparency | crt.sh (current) | Tier 1 |
| company_registry | SEC EDGAR, GLEIF, OpenCorporates (current) | Mixed Tier 1/3 |
| sanctions_multi | OpenSanctions (current) | Tier 3 |
| geoint_local | ExifTool, DeepFace, InsightFace, Overpass, SunCalc (current) | Tier 1; local/image analysis stays limited to its documented scope |

Phase 9 remains a separate future planning list: dns_records, certificate_transparency, threat_intel, ip_geolocation, whois_multi, paste_search, code_search, sanctions_multi, company_registry, archive_lookup, search_engines, academic_search, news_search, vehicle_vin, flight_tracking, maritime_ais, historical_weather, and social_public_json.

## Deliverables when implemented

- Manifest metadata for every adapter and construction-time rejection of Tier 4/5.
- Router behavior that dispatches matching Tier 1/2 adapters unconditionally and records missing Tier 3 keys as skips.
- Optional lawful-basis declaration recording, without blocking the run when it is empty.
- Informational jurisdiction warnings and a full audit trail on every run.
- Reports that list adapters run, skipped, and the reason for each skip.
- Tier, source, license, rate-limit, grouping, and verification metadata maintained with each adapter.

## What this is not

- Not an implementation task or a statement that the current CLI supports the target behavior.
- Not permission to violate law, collect private data, or disregard a source's access controls.
- Not permission to ingest plaintext credentials, stolen tokens, or criminal-market content.
- Not a change to storage, egress control, audit integrity, or verification claims.
- Not authorization to implement the proposed Phase 5b or Phase 5c tools without their own scoped review.

## Phase 5c source-check snapshot

The proposed list supplied with this direction names 19 tools although it calls the list 20. No twentieth tool has been inferred. Primary-source checks and outcomes are recorded in [PHASE_5C_REGISTRY.md](PHASE_5C_REGISTRY.md). A source check verifies public documentation or repository facts; it does not verify a future Aletheia adapter or a live tool run.
