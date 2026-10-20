# Rate Limits, Authentication and Scope: pgp_keys (WKD)

`pgp_keys` performs one OpenPGP Web Key Directory lookup for one email address. It sends no credentials and stores no key material.

## Specification and endpoints

- Reviewed specification: [draft-koch-openpgp-webkey-service-22](https://datatracker.ietf.org/doc/html/draft-koch-openpgp-webkey-service) (2026-10-20).
- Advanced method: `GET https://openpgpkey.<domain>/.well-known/openpgpkey/<domain>/hu/<z-base-32(SHA-1(local-part))>?l=<local-part>`
- Direct method: `GET https://<domain>/.well-known/openpgpkey/hu/<same-hash>?l=<local-part>`
- The local-part is ASCII-lowercased only for the SHA-1 hash. The `l` query parameter preserves the original local-part and is percent-encoded. The domain is IDNA-encoded for the URL.
- The specification's sample vector is used in the self-test: `Joe.Doe` hashes to `iy9q119eutrkn8s1mk4r39qejnbu3n5q`.

## Method and fallback

The adapter tries the advanced method first. It tries the direct method **only when DNS resolution of `openpgpkey.<domain>` fails**, as the specification requires. An HTTP 404 from the advanced method is a negative result, not a reason to fall back. Redirects are followed only if the final response is still HTTPS.

## Authentication and rate limits

- No Authorization header, API key, account, or client certificate. A 401/403 challenge is reported as an error.
- WKD defines no numeric client quota. This adapter makes one request per lookup, or two only on the DNS fallback; it never retries, paginates, rotates proxies, or parallelises lookups.
- 30-second timeout and a 2 MB response cap. The raw response is hashed with SHA-256 for provenance and is not otherwise retained.

## Data minimisation

Emitted: the requested email, the method and URL used, the HTTP status, the response SHA-256/length, and for each matching primary key the OpenPGP fingerprint, key ID, version, public algorithm, creation time, matching User ID(s), and the count of non-matching User IDs.

Not emitted: key material, signatures, subkeys, revocation state, non-matching User IDs, or any private data. The parser accepts OpenPGP v4 primary keys and rejects partial packet lengths, indeterminate lengths, and unsupported key versions with a bounded error.

Only User IDs containing the requested email are retained; all other User IDs are dropped, following the specification's client rule.

## Interpretation limits

A WKD response shows that a domain publishes an OpenPGP key for an email address. It does not prove that the key is valid, unrevoked, unexpired, or controlled by a particular person. This adapter does not verify signatures or check revocation; it reports published key metadata only. No live target is on file; verification is fixture-based against the official specification's sample key.

## Version pin

The container is `python:3.13-slim-bookworm`; the parser is standard-library only. The descriptor is pinned to `1.0 (WKD draft-koch-openpgp-webkey-service-22; reviewed 2026-10-20)`.

## Verification

- No live target is on file. The synthetic fixture `tests/fixtures/pgp_keys.json` mirrors a normalized WKD response; the driver self-test parses the official specification's sample key and checks the known fingerprint `B21DEAB4F875FB3DA42F1D1D139563682A020D0A`, its EdDSA algorithm, and the matching User ID.
- `--normalize` re-validates the fixture offline. `--health` and `--selftest` make no network requests.
