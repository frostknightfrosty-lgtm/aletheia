# Directive Amendment — Florida Project Framework

Base jurisdiction for Aletheia's project policy: Florida, USA. This amendment
supersedes the previous grey posture and five-tier policy. It records project
defaults; it is not legal advice or a complete statement of Florida or federal
law. The project defaults do not override applicable statutes, court orders,
source access controls, contracts, or individual rights.

Florida statutes address conduct beyond the four project-floor categories,
including computer access, communications, and stalking. Public scraping or a
terms-of-service dispute is not categorically lawful or only civil; outcomes
depend on the facts and applicable law. See the [Florida Computer Crimes Act,
Fla. Stat. § 815.06](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&Search_String=815.06&SubMenu=1&URL=0800-0899%2F0815%2FSections%2F0815.06.html),
[Fla. Stat. § 934.03](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&Search_String=&URL=0900-0999%2F0934%2FSections%2F0934.03.html),
and [Fla. Stat. § 784.048](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&Search_String=163&URL=0700-0799%2F0784%2FSections%2F0784.048.html).

## Project hard floor (Tier 5 — forbidden)

- Unauthorized computer access, including using another person's credentials or bypassing CAPTCHAs/paywalls
- Communications interception
- Criminal marketplace transactions
- Stalking or harassment

These four categories define Aletheia's Tier 5 policy floor. Their enumeration
does not imply that other conduct is lawful or free of civil, contractual, or
regulatory consequences.

## Tier system

| Tier | Category | Project default |
|---|---|---|
| 1 | Public, unauthenticated, no ToS concern | On |
| 2 | Public, ToS-hostile to automation | On |
| 3 | Requires free API key | On when key is present |
| 4 | Leak indexes, aggregators, plaintext credential sources, dark-web indexes, stealer logs | On |
| 5 | The four prohibited categories above | Off |

Tier defaults describe Aletheia policy, not legal conclusions about a source or
investigation. Check current laws, source terms, authorization, and deployment
context before use.

## Policy calls already made

- GHunt — allowed when using only the operator's own Google account
- Face search (PimEyes, FaceCheck.ID, Search4Faces, Lenso.ai) — allowed by project policy
- People-search aggregators (TruePeopleSearch, Whitepages free, PeekYou) — allowed; paid-only products rejected
- Stealer-log checkers (including Hudson Rock Cavalier and LeakRadar) — allowed by project policy
- Dark-web search engines (Ahmia, Torch, OnionLand, DarkSearch) — allowed by project policy
- Tools requiring the operator's own authenticated account — allowed when the account owner authorizes the use
- Plaintext credential storage — allowed by project policy; credential parsing/storage must remain structurally separated from authenticated HTTP code
- Bulk data processing — allowed by project policy, subject to applicable limits and source restrictions
- Public-site scraping, including where automation terms are hostile — allowed by project policy; this does not establish that a particular use is lawful or only a civil matter

Permission under this policy does not mean the capability is implemented,
verified, or suitable for all targets. Each adapter still needs its own source,
license, scope, and implementation review.

## Previously excluded sources, now allowed by project policy

LeakCheck, LeakRadar, OsintCat, OathNet, Blackbird, Lullar, and Hudson Rock.
They are not thereby integrated or verified. Their current implementation
status and remaining source-review facts are recorded in the registries and
`docs/NOT_INTEGRATED.md`.

ONYPHE remains excluded because its Free View terms restrict use to the
operator's own systems, which does not fit the project's general investigative
use case.

## Structural rule

Code that parses and stores credential values must not share a module or
interface with code that makes authenticated HTTP requests. Those paths must
not share an HTTP client that could be directed to a login endpoint. This is a
code-level separation requirement; it does not authorize logging into another
person's account or attempting credentials against services.

## Adapter safety rule

LinkedIn-enumeration-style adapters (CrossLinked, InSpy, and similar tools) may
output only `name`, `username`, `email`, `company`, and `source_url`. They must
not emit password patterns, perform login attempts, or access authentication
endpoints. Do not integrate a tool if it cannot be constrained to read-only
output.
