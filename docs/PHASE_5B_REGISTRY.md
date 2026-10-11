# Phase 5b Adapter Registry

This registry tracks Phase 5b source scope and implementation status; it is not approval to run tools against arbitrary targets. XposedOrNot implementation is in progress and pending CI. PhoneInfoga's existing adapter still needs scope confirmation; Blackbird and Lullar remain unverified proposals. LeakCheck was excluded by the project owner on 2026-10-11. Hudson Rock, osint-darkweb-pkg, and DarkNyx were excluded after their published call paths could not be verified to stay within the project's Tier 1–2 content boundary; see `NOT_INTEGRATED.md`.

## xposedornot

~~~yaml
name: xposedornot
input_types: [email]
output_schema: BreachRecord[]  # breach name, year, data classes
invocation: api
requires_key: false
rate_limit: "25/hour, 100/day per IP"
legal_tier: 2
legal_notes: "Free community API for personal, low-volume use. Query only an authorized email, obey the published request caps, and do not bulk collect or redistribute breach data."
scope_constraint: "Use only GET https://api.xposedornot.com/v1/check-email/{email} with details omitted or false. Store only the echoed query email and breach names; do not call analytics, password, or domain endpoints. The documented community endpoint is free and capped at 25 requests/hour and 100/day per IP."
implementation_status: in_progress; CI pending
fixture_provenance: documentation example at https://xposedornot.com/api_doc; modeled fixture is marked synthetic
verification_status: unknown
enabled_by_default: true
batch_grouping: breach_search
~~~

The endpoint, default response fields, and published rate limit were checked against the official API documentation. No live request was made because no authorized email target was supplied for this check. The adapter parses names only; it does not access detailed breach or password endpoints.

## phoneinfoga — existing adapter, scope confirmation proposed

~~~yaml
name: phoneinfoga
input_types: [phone]
output_schema: PhoneFootprint[]  # country, carrier, line type, web footprints
invocation: local_python  # CLI plus local REST API
requires_key: false
legal_tier: 1
legal_notes: "Proposal claims free public resources only. Keep browser/login workflows and target-side actions unavailable."
fixture_provenance: https://github.com/sundowndev/phoneinfoga
verification_status: unverified-live
enabled_by_default: true
batch_grouping: phone_intel
~~~

PhoneInfoga already exists in the current registry and has fixture coverage, but no live adapter verification is claimed here. This entry proposes confirming its metadata for the new tier model.

## blackbird

~~~yaml
name: blackbird
input_types: [username, email]
output_schema: AccountHit[]  # platform, profile URL
invocation: local_python  # CLI
requires_key: false
rate_limit: "daily usage cap"
legal_tier: 2
legal_notes: "Proposal describes public-profile endpoint enumeration. Do not bypass login, CAPTCHA, rate limits, or access controls."
fixture_provenance: https://github.com/p1ngul1n0/blackbird
verification_status: unverified-live
enabled_by_default: true
batch_grouping: username_enum
~~~

Current package identity, license, maintenance date, and actual free-use limits need to be pinned before implementation.

## lullar

~~~yaml
name: lullar
input_types: [username, email, name]
output_schema: AccountHit[]  # proposed 170+ platforms
invocation: web_scraper  # fragile
requires_key: false
legal_tier: 2
legal_notes: "Proposal describes a web-only scraper. Every request must remain unauthenticated, respect applicable law, and stop on access controls or blocking."
fixture_provenance: pending verification
verification_status: unverified-live
enabled_by_default: true
batch_grouping: people_search
~~~

No official source, license, stable endpoint, or maintenance record was verified for this proposal in this task. Its stated fragility makes silent parser failure a known design risk.

## Implementation gate

Before implementation, each entry needs a pinned official source, license and version review, current maintenance date, permitted invocation, rate limit, legal tier, response-field screening, and a real authorized fixture. A fixture must not be fabricated from an assumed upstream schema.
