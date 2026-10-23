# SpiderFoot 4.0 curated module catalogue

Phase 18.2 adds SpiderFoot as a **batch meta-adapter**, not as a replacement for
Aletheia's native adapters. The image is pinned to SpiderFoot v4.0.0 commit
`b9c345de5b085debc7444fc10e0e26e7745df5f2`. The runner enables only the 14
modules below, so a scan cannot silently expand into SpiderFoot's full 200+
module catalogue.

## Selection principle

A module is included only when it adds a source, pivot, or classification that a
native Aletheia adapter does not already provide. Modules whose output duplicates
a native adapter are excluded even if they are individually useful. Every
finding produced by these modules is tagged `source_priority: "secondary"` by
the Aletheia adapter; a native observation always wins the same field.

## Curated modules

| # | SpiderFoot module | Data source | Gap filled | Tier | Key |
|---:|---|---|---|---:|---|
| 1 | `sfp_threatcrowd` | ThreatCrowd | Passive domain/IP/email reputation and related infrastructure | 1 | none |
| 2 | `sfp_threatminer` | ThreatMiner | Passive DNS, WHOIS, and malware-family context | 1 | none |
| 3 | `sfp_robtex` | Robtex | Shared hosting and passive DNS adjacency | 1 | none |
| 4 | `sfp_keybase` | Keybase | Public key/identity proofs and linked accounts | 1 | none |
| 5 | `sfp_openphish` | OpenPhish | Current phishing URL feed matching | 1 | none |
| 6 | `sfp_phishtank` | PhishTank | Verified phishing URL and target matching | 1 | none |
| 7 | `sfp_threatfox` | ThreatFox (abuse.ch) | Recent malware IOC and C2 matching | 2 | none |
| 8 | `sfp_abusech` | abuse.ch | Feodo/SSL/URLhaus abuse-feed matching | 2 | none |
| 9 | `sfp_emailrep` | EmailRep | Email reputation and public-profile signals | 3 | `EMAILREP_API_KEY` |
| 10 | `sfp_hunter` | Hunter | Public business-email and domain association | 3 | `HUNTER_API_KEY` |
| 11 | `sfp_pulsedive` | Pulsedive | Risk-scored indicator enrichment | 3 | `PULSEDIVE_API_KEY` |
| 12 | `sfp_intelx` | Intelligence X | Leak-index and historical exposure lookup | 4 | `INTELX_API_KEY` |
| 13 | `sfp_c99` | C99 | Commercial subdomain/recon API enrichment | 4 | `C99_API_KEY` |
| 14 | `sfp_haveibeenpwned` | Have I Been Pwned | Breach-index confirmation for an email address | 4 | `HIBP_API_KEY` |

The keyed modules consume the same secret names used by Aletheia's existing
leak/email adapters. `HIBP_API_KEY` is shared deliberately; no key is copied into
the repository, the image, a command line, or an evidence artifact.

## Descriptive legal tiers

The tier is logged with every module finding and in the runner envelope. **It is
descriptive, not a blocking gate.** The runner does not refuse a module because
of its tier. The Operator-Driven Model makes the operator responsible for
authorization, source terms, quota compliance, and the decision to enable keyed
or leak-index modules.

| Tier | Label | Meaning |
|---:|---|---|
| 1 | `public no-auth passive` | Public, unauthenticated source; still subject to that source's terms and rate limits |
| 2 | `public abuse feed, no auth` | Public abuse/blocklist feed; results may be historical or stale |
| 3 | `free authenticated, rate limited` | Free account/API key; quota and terms apply |
| 4 | `commercial or leak-index source` | Paid API or leak-index source; operator must hold authorization and comply with source terms |
| 5 | `aggressive scraping / operator-authorized` | Reserved for a future explicitly selected scraping module. No current module is assigned tier 5; the runner has no tier-based block |

A tier-4 module is allowed to run when its key is present. A tier-4 module with
no key is skipped with an explicit reason rather than producing a silent gap.
Tier 5 is documented so an operator can add a module without changing the
runner's tier semantics; no uncurated module is enabled by this phase.

## Seed mapping

SpiderFoot's `-s` target detection is separate from `-t` event filtering. The
runner validates the seed, then maps it as follows:

| Aletheia seed | SpiderFoot `-s` value | `-t` event type |
|---|---|---|
| `domain:example.com` | `example.com` | `INTERNET_NAME` |
| `ip:8.8.8.8` | `8.8.8.8` | `IP_ADDRESS` |
| `email:test@example.com` | `test@example.com` | `EMAILADDR` |
| `username:frost2233` | `"frost2233"` (quoted target) | `USERNAME` |
| `phone:+15551234567` | `+15551234567` | `PHONE_NUMBER` |

The domain is detected by SpiderFoot as `INTERNET_NAME`; `DOMAIN_NAME` is the
output event that the adapter maps to the Aletheia `domain` entity. Usernames are
quoted because SpiderFoot otherwise treats a dotted username as a domain.

## Invocation contract

For a seed and the runnable subset `<modules>`:

```text
python3 sf.py -s <seed> -t <spiderfoot-event-type> -o json -q -m <modules>
```

`-q` suppresses logging so stdout remains the JSON event array. SpiderFoot's
`sfp__stor_stdout` module writes that array, and the runner wraps it in an
envelope:

```json
{
  "source": "spiderfoot",
  "version": "4.0.0",
  "commit": "b9c345de5b085debc7444fc10e0e26e7745df5f2",
  "status": "ok",
  "seed": {"type": "domain", "value": "example.com", "spiderfoot_type": "INTERNET_NAME"},
  "modules_requested": ["sfp_threatcrowd", "..."],
  "modules_run": ["sfp_threatcrowd", "..."],
  "skipped": [
    {"module": "sfp_hunter", "source": "Hunter", "requires_key": true,
     "env": "HUNTER_API_KEY", "legal_tier": 3,
     "reason": "HUNTER_API_KEY is not set"}
  ],
  "api_keys_injected": 0,
  "events": [],
  "errors": [],
  "scan_exit_code": 0,
  "stderr_tail": ""
}
```

The parser accepts both this envelope and a raw SpiderFoot JSON event array. A
missing key produces a skip record in the envelope and a secondary technical
finding with `details.skipped=true` in Aletheia, so the coverage report can name
the gap. `stderr_tail` is diagnostic text only; it is not evidence.

## API-key handling

1. The runner checks each keyed module's environment variable.
2. If absent, the module is removed from `-m` and the skip reason is recorded.
3. If present, SpiderFoot's schema is initialized in `/tmp/spiderfoot` and the
   key is written to `tbl_config` (`scope=<module>`, `opt=api_key`) in the
   private SQLite database.
4. The scan runs with `SPIDERFOOT_DATA=/tmp/spiderfoot`; keys are never passed
   in argv.
5. After the child process exits, the runner deletes `api_key` rows from
   `tbl_config`. The root filesystem remains read-only under Aletheia's Docker
   wrapper; only the `/tmp` tmpfs is writable.

The image does not contain any API key. `docker run` receives only the
environment variable names selected by the adapter descriptor; Aletheia's
execution wrapper passes their values through Docker without writing them to
argv or audit logs.

## Deliberate exclusions

These are not enabled because they duplicate native adapters or expand scope
without adding a gap:

- `sfp_shodan` — overlaps the native Shodan adapter.
- `sfp_github` / `sfp_gravatar` — overlap native GitHub identity and Gravatar.
- `sfp_leakix` — overlaps the native leak-checkers batch.
- `sfp_haveibeenpwned` is the one leak-index exception because the native path
  benefits from a direct breach-index confirmation; it is key-gated and tier 4.
- Full-catalogue scanning, search-engine scraping, and modules requiring
  CAPTCHA, OAuth, or login bypass are not enabled. No CAPTCHA/Cloudflare/OAuth
  bypass is implemented.

## Health check

The Docker verification case `phase18-spiderfoot-health` runs the image with
`--network none` and the runner's `--health` mode, which invokes:

```text
python3 sf.py -h
```

This validates the pinned source tree, dependency imports, and entrypoint without
performing any network request.
