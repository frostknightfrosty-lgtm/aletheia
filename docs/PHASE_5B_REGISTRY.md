# Phase 5b Adapter Registry

This is a proposal registry, not an implementation or approval to run these tools. Seven proposals remain; all are unverified-live. LeakCheck was excluded by the project owner on 2026-10-11 and is documented in `NOT_INTEGRATED.md`. No Phase 5b adapter code, Docker image, parser, or live run was added by this documentation change.

## xposedornot

~~~yaml
name: xposedornot
input_types: [email]
output_schema: BreachRecord[]  # breach name, year, data classes
invocation: api
requires_key: false
rate_limit: "25/hour, 100/day per IP"
legal_tier: 1
legal_notes: "Free public API, no key, ToS permits programmatic querying."
fixture_provenance: https://xposedornot.com/api_doc
verification_status: unverified-live
enabled_by_default: true
batch_grouping: breach_search
~~~

The supplied API documentation URL is a fixture/source lead only; the integration and stated rate limits have not been live-verified.

## hudsonrock

~~~yaml
name: hudsonrock
input_types: [email, username, domain, ip]
output_schema: StealerLogSignal[]  # infection telemetry, boolean signals, no plaintext
invocation: api
requires_key: false  # shallow-query proposal
legal_tier: 1
legal_notes: "Proposed shallow query returns infection signals only; do not return credentials or tokens."
fixture_provenance: pending verification
verification_status: unverified-live
enabled_by_default: true
batch_grouping: breach_search
secondary_batch_grouping: stealer_log
~~~

No source response or fixture was independently verified in this task. Before any implementation, confirm the free endpoint, data fields, rate limits, terms, and that the shallow response cannot expose plaintext.

## osint-darkweb-pkg

~~~yaml
name: osint-darkweb-pkg
input_types: [keyword, domain, email, onion]
output_schema: DarkWebHit[]  # engine, snippet, onion URL
invocation: local_python  # proposed local Tor SOCKS5 dependency
requires_key: false
legal_tier: 1
legal_notes: "Proposal claims public Tor index-engine queries. No credentials, criminal-market content, or unlawful access may be collected."
fixture_provenance: pending verification
verification_status: unverified-live
enabled_by_default: true
batch_grouping: darkweb_search
~~~

The tool identity, source coverage, license, and boundaries of public/indexed content remain unverified.

## darknyx

~~~yaml
name: darknyx
input_types: [keyword, btc, eth, xmr, ip, cve, iban, pgp, onion]
output_schema: DarkWebEntity[]  # category, snippet, onion URL, ransomware feed
invocation: api  # proposal says public read-only or self-hosted
requires_key: false
legal_tier: 1
legal_notes: "Proposal claims public read-only entity search. Exclude credentials, stolen tokens, and criminal-market content."
fixture_provenance: pending verification
verification_status: unverified-live
enabled_by_default: true
batch_grouping: darkweb_search
~~~

The exact upstream project, API, license, maintenance state, and free access path require verification.

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
