# Rate Limits for ip_intelligence Batch Adapter Sub-Sources

Each sub-source's current rate limits as documented in official sources. Verified 2026-10-12.

| Sub-source | Rate Limit | Source URL |
|---|---|---|
| IPinfo API | Free Lite tier: unlimited requests (no daily/monthly cap). Legacy public API (no key): 1,000 req/day shared across IP. | https://ipinfo.io/developers |
| IP-API | 45 req/min per IP. HTTP 429 on excess; persistent abuse leads to 1-hour ban. Headers: `X-Rl` (remaining), `X-Ttl` (seconds to reset). | https://ip-api.com/docs/api:xml |
| ipapi.co | Free tier: 1,000 req/day (approx 30K/mo). Not for production. Heuristics may further restrict. | https://ipapi.co/pricing/ |
| IPGeolocation.io | Free/Developer plan: 1,000 credits/day (hard limit, no overage). No per-minute/hourly limits. `X-Credits-Charged` header per request. | https://ipgeolocation.io/documentation.html |
| AbuseIPDB API v2 | Free Individual: 1,000 checks/day (resets 00:00 UTC). Webmaster: 3,000/day. Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`. | https://docs.abuseipdb.com/ |
| GreyNoise Community API | Unauthenticated: 10 IP lookups/day. Free tier (business email): 50 lookups/week. Community API returns 429 with `plan` and `rate-limit` fields. | https://docs.greynoise.io/docs/using-the-greynoise-community-api |
| VirusTotal API v3 | Public API: 4 req/min, 500 req/day, ~15,500 req/mo. Resets 00:00 UTC. Must not use in commercial products. | https://docs.virustotal.com/reference/public-vs-premium-api |
| URLhaus Community API | Free Auth-Key required. "Fair use principles" — typically a few hundred submissions and a few thousand reads per day. No explicit numeric quota published. Heavy users should batch and cache. | https://urlhaus.abuse.ch/api/ |
| ThreatFox Community API | Free Auth-Key required. "Fair use principles" — no explicit numeric quota published. Same abuse.ch Auth-Key as URLhaus. | https://threatfox.abuse.ch/api/ |
| MalwareBazaar Community API | Free Auth-Key required. File downloads: 2,000 per IP/day. Query results capped at 1,000 per request. "Fair use principles" for queries. | https://bazaar.abuse.ch/api/ |
| PhishTank API | Optional free `app_key`. Without key: "much more limited" (exact numbers not published). With key: higher limits via response headers `X-Request-Limit-Interval`, `X-Request-Limit`, `X-Request-Count`. HTTP 509 on limit. | https://www.phishtank.com/api_info.php |
| Netlas API | Community (free): 50 requests/day, 2,500 search results/month. API: 60 req/min for search/count (excl. certs), 3 req/min for certificate searches. `Retry-After` header on 429. | https://docs.netlas.io/api-reference/ |
| FullHunt API | Free tier: 10 credits/month (1 credit = 1 request). Route-specific rate limits: host lookup 10/min, global search 60/min, domain subdomains/details 200/hr. | https://docs.fullhunt.io/rate-limiting |
| HackerTarget API | Free: 50 API calls/day per IP, max 2 req/s. HTTP 429 on excess. No auth required. | https://hackertarget.com/ip-tools/ |
| ipinfo.app ASN Lookup | No auth required. Search endpoints: soft limit 30 req/min per IP. IP-to-ASN lookups cached 1 week. No hard daily limits for reasonable use. | https://asn.ipinfo.app/api/ |

---

**Notes:**

- "Fair use" sources (URLhaus, ThreatFox, MalwareBazaar queries) do not publish hard numeric quotas. Implement conservative client-side pacing (e.g., 1 req/sec) and respect 429/5xx with exponential backoff.
- Several sources (IPinfo, GreyNoise, VirusTotal, Netlas, FullHunt) expose rate-limit headers (`X-RateLimit-*`, `Retry-After`). The runner should parse and honor these.
- All free tiers are for non-commercial/personal use per their terms. The adapter runs only when an authorized investigation seed is provided.
- The batch adapter queries each sub-source once per run (single IP/CIDR input), so per-run quota consumption is minimal (≤15 requests).