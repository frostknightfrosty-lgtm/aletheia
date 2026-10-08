# Phase 4 — Identity, Email, Phone

Phase 4 adds seven adapters under the same provenance/checkpoint/Docker contract.

## Adapters

- Maigret 0.6.6 — username enumeration, MIT.
- Holehe 1.61 — email account-registration signals, GPL-3.0.
- h8mail 2.5.6 — email breach/recon aggregation, BSD-3-Clause. The wrapper disables local breach files, custom queries, chasing, and password output.
- HIBP API v3 — authenticated breach-account lookup. The API requires an HIBP API key and identifying User-Agent.
- PhoneInfoga 2.11.0 — phone-number scan command, GPL-3.0.
- libphonenumber 9.0.40 — offline parsing/validation, Apache-2.0.
- Twilio Lookup v2 — Basic Lookup only; additional paid packages are not requested.

## Legal policy

All personal-identifier adapters require `authorization_assertion` in the Aletheia request. The assertion is checkpointed. The wrapper does not bypass login, CAPTCHA, paywall, or WAF controls, and does not invoke password-retrieval flows beyond what an upstream module itself documents as its public account-registration signal.

No password contents are ingested into the normalized graph. h8mail local breach-file modes and premium/custom query modes are deliberately unavailable through this adapter.
