# Rate Limits for government_records_us Batch Adapter Sub-Sources

Each sub-source's current rate limits as documented in official sources. Verified 2026-10-13.

| Sub-source | Rate Limit | Source URL |
|---|---|---|
| FINRA BrokerCheck | 1,200 req/min per IP (sync); 20 req/min per dataset per account (async). Default 1,000 records per response. | https://developer.finra.org/docs |
| FDIC BankFind Suite API | 1,000 req/hour per API key (via api.data.gov). Default limit 10, max 10,000 per request. | https://banks.data.fdic.gov/docs/ |
| Federal Reserve Enforcement Actions | Static JSON feeds (ea-old.json, ea-cms-recent.json). No API rate limits; no auth required. | https://www.federalreserve.gov/supervisionreg/enforcementactions.htm |
| OCC Enforcement Actions Search | Free api.data.gov key required. 1,000 req/hour default; DEMO_KEY: 30 req/hour, 50/day. | https://api.occ.gov/ |
| USAspending API | No auth required. Community reports ~1,000 req/300 sec (5 min) for most endpoints. No fixed published limits. | https://api.usaspending.gov/ |
| SAM.gov APIs | api.data.gov key: 1,000 req/hour default; DEMO_KEY: 30 req/hour, 50/day. Entity API: 10/day (no role) to 10,000/day (federal system). | https://api.data.gov/docs/developer-manual/ |
| Lobbying Disclosure Act API | Anonymous: 15 req/min. Registered key: 120 req/min. Max 25 results per page. | https://lda.gov/api/tos/ |
| FOIA.gov API | api.data.gov key: 1,000 req/hour default; DEMO_KEY: 30 req/hour, 50/day. | https://www.foia.gov/developer/ |
| NHTSA vPIC | No auth. No fixed daily limit. Automated traffic control; ~1,000-2,000 txn/min capacity. Microsoft connector: 100 req/60 sec per connection. Batch: max 50 VINs/request. | https://vpic.nhtsa.dot.gov/api/Home/Index/FAQ |
| Federal BOP Inmate Locator | Public JSON endpoint (no auth). No official rate limits. APIs.io: 10 req/min, 1,000/month free tier. Scraper implementations: 10 req/day free, 100 records/query cap. | https://www.bop.gov/PublicInfo/execute/inmateloc |
| NYC Open Data (SODA) | Anonymous: 500 req/hour. Free app token: 1,000 req/hour. Max 50,000 records/page, default 1,000. | https://dev.socrata.com/docs/throttling.html |

---

**Notes:**

- Several sources use `api.data.gov` keys (FDIC, OCC, SAM.gov, FOIA.gov) — same key works across all, shared 1,000 req/hour quota.
- FINRA BrokerCheck has high limits (1,200/min) suitable for single-query-per-run usage.
- USAspending, Federal Reserve, and OCC enforcement have no fixed limits; implement conservative backoff.
- BOP Inmate Locator and NHTSA vPIC have no hard published limits; implement exponential backoff on 429/5xx.
- All sources are free (Tier 1-3). The adapter queries each at most once per run, so per-run quota consumption is minimal (≤11 requests).
- Rate-limit headers (`X-RateLimit-*`, `Retry-After`) should be parsed and honored where present.