# Phase 3 — Domain / Infrastructure Adapters

Phase 3 adds ten adapters to the Phase 1 core while preserving the adapter boundary and Phase 2 provenance model.

| Adapter | Pin | License | Collection mode |
|---|---|---|---|
| Amass | 5.1.1 | Apache-2.0 | Passive enumeration wrapper |
| Subfinder | 2.17.0 | MIT | Passive subdomain sources |
| Assetfinder | 0.1.1 | MIT | Passive asset discovery |
| DNSX | 1.3.1 | MIT | Authorized DNS resolution |
| MassDNS | 1.1.0 | GPL-3.0-only | Authorized DNS resolution |
| DNSRecon | 1.6.3 | GPL-2.0-only | Authorized standard/CT enumeration |
| Fierce | 1.6.0 | GPLv3 | Authorized DNS reconnaissance |
| Shodan | 1.31.0 Python library | MIT | Licensed API lookup |
| Censys | Platform API v3 | Apache-2.0 tooling | Licensed indexed-data API |
| crt.sh | Public endpoint | Service endpoint | Certificate-transparency search |

DNSX, MassDNS, DNSRecon, and Fierce require an explicit `authorization_assertion`. The wrappers deliberately omit brute-force/range/wide scanning and other broader modes.

For CLI collectors that do not expose a per-record primary source URL, the finding retains the upstream tool URL as **collector provenance**, hashes the raw artifact, and records that limitation in the finding notes. Aletheia does not claim that a tool homepage is the underlying primary source.

Shodan and Censys credentials are passed through the descriptor's explicit secret environment allowlist and never appear in commands or finding JSON. Censys Platform API uses bearer PAT authentication; organization ID is optional and can be supplied through `CENSYS_ORG_ID`.
