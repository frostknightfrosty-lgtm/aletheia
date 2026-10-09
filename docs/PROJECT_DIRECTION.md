# Aletheia Project Direction

> This is a strategic shift that governs Phase 8 and beyond. It is not an instruction to implement now: the live investigation is still in flight, and Phase 8's original plan—egress proxy and storage backends—comes first. Record this direction for future sessions.

## Purpose

Aletheia's current legal posture is defensive legal — the standard a law firm would demand for a court case. That is much tighter than what is legally required, and it has cost significant capability. The project direction is to move from "court-defensible" to "clearly legal," and to reclaim every capability that extra caution was costing.

The default operating mode is Mode 2 (Personal) — deliberate but not obstructive. Mode 1 (Open) is a fast path available on demand. Mode 3 (Sensitive) is a hard stop that requires justification.

## The three-tier model

### Mode 2 — Personal (DEFAULT)

- All Tier 1 and Tier 2 sources run.
- Requires a one-line declaration of lawful basis (replaces the current `--authorization-assertion`).
- Logged in the audit trail.
- Covers both public infrastructure and personal-identifier sources.
- This is the mode Aletheia runs in unless the operator explicitly overrides it.

### Mode 1 — Open (explicit opt-in, fast path)

- Runs all Tier 1 sources immediately. No prompts. No assertions. No gating.
- Invoked by a single top-level flag, e.g. `--mode open` or `--open`, on the first line of the invocation.
- Intended for domain, corporate, and infrastructure investigations where no personal data is touched.
- This is the SpiderFoot-equivalent mode. It is not the default, but it is one flag away.
- Does not run Tier 2 or Tier 3 sources. For those, the operator must use Mode 2.

### Mode 3 — Sensitive

- Breach data, biometrics, protected classes, minors, GDPR-relevant subjects.
- Requires explicit justification beyond the standard declaration. Warns if the subject is in a jurisdiction with strong privacy law. Produces a full audit trail.
- Rarely used. Hard to reach by accident.

## Tier definitions for sources

| Tier | Description | Legal status |
| --- | --- | --- |
| 1 | Public, unauthenticated, no ToS concern | Legal everywhere. No gating in any mode. |
| 2 | Public but ToS prohibits scraping (hiQ v. LinkedIn territory) | Legal in US, murky in EU/UK. Jurisdiction-gated. Runs in Mode 2 (default) and Mode 3. |
| 3 | Requires an API key, used in ToS compliance | Legal if you follow the ToS. Runs when key is provided in Mode 2 or Mode 3. |
| 4 | Requires consent or warrant — logged-in data, private data, intercepted communications | Never implemented. Hard floor. |
| 5 | Auth bypass, leaked databases, GDPR with no basis | Never implemented. Hard floor. |

## What to change

- Make Mode 2 (Personal) the default for the CLI. An operator who runs `aletheia investigate --seed ...` without specifying a mode gets Mode 2.
- Add a single top-level flag for Mode 1 (suggest `--mode open` or a shorthand `--open`) that skips the lawful-basis declaration and runs all Tier 1 sources without gating. This is the fast path.
- Keep `--legal-only` as an alias for Mode 3, or deprecate it with a clear migration note. Do not silently change its meaning.
- Remove `--purpose` / `--authorization-assertion` requirements from all Tier 1 sources when Mode 1 is active. Under Mode 2, keep the single-line declaration, but make it a short flag rather than a long prose field.
- Remove legal-only gating from infrastructure and corporate adapters in all modes except Mode 3.
- Raise rate limits to each API's ToS maximum rather than conservative floors.
- Enable Tier 1 adapters by default in every mode.
- Allow Tier 2 scraping behind a jurisdiction flag (US: on; EU/UK: warns and defaults off).
- Allow Tier 3 APIs freely once a key is provided.
- Keep the audit log, provenance graph, and resumability — those remain the defensibility feature and are not in conflict with breadth.

## What stays out of scope forever

- No bypassing authentication.
- No CAPTCHA solving.
- No paywall circumvention.
- No accessing leaked databases.
- No bulk personal-data collection without a lawful basis in the relevant jurisdiction.
- No minors, no health data, no interception.

## Breadth strategy

To close the gap with SpiderFoot's free-tier breadth without adding 170 Docker containers:

Build batch adapters — one adapter per category, running many small sub-checks against one class of free endpoints.

Examples of planned batch adapters: `dns_records` (SPF, DMARC, DKIM, MX, TXT, CAA, DNSSEC), `certificate_transparency` (crt.sh, CertSpotter, Facebook CT), `threat_intel` (AbuseIPDB, AlienVault OTX, GreyNoise, ThreatCrowd, URLhaus), `ip_geolocation` (ipinfo, ip-api, ipapi.co, MaxMind), `paste_search` (psbdmp, Pastebin, dpaste), `code_search` (GitHub, GitLab, grep.app, searchcode), `archive_lookup` (Wayback CDX, Common Crawl, archive.today), `academic_search` (OpenAlex, Crossref, Semantic Scholar, arXiv, PubMed), `news_search` (GDELT, NewsAPI, MediaCloud), and others.

18 batch adapters can replace roughly 70 SpiderFoot modules within 25–30 total containers.

Same architecture: one Dockerfile, one adapter, many sub-checks, normalized output into the graph.

Same provenance, same audit, same resumability.

## Deliverables when this direction is implemented (Phase 8.x or later)

- `tiers.json` — every adapter classified Tier 1/2/3 with a one-line justification.
- `--mode {open|personal|sensitive}` CLI flag with personal as the default.
- A single-line fast-path flag for Mode 1, e.g. `--open`, usable as the first line of the invocation.
- Jurisdiction setting in config, defaulting to user locale.
- Rate-limit config defaulting to ToS ceilings.
- README section documenting what each mode does and its legal assumptions — for the operator, not the tool.
- First wave of batch adapters (10 from the Tier 1 list above).
- A source registry where each sub-check has a status, license, rate limit, and enabled-by-default flag.

## What this is not

- Not a license to do anything illegal.
- Not a reversal of the audit findings — those gaps still need fixing.
- Not a replacement for Phase 8's egress proxy and storage work.
- Not an instruction to implement now.

It is a correction of posture: make the default deliberate but not obstructive, give the operator a one-flag fast path to full public-source breadth, and spend legal friction only where it earns its keep.
