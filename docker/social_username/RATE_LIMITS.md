# Social username source limits and scope

The runner makes no live requests during `--health`. A normal username run makes at most one
request to each enabled source, uses a five-second timeout, disables redirects and environment
proxy use, and never retries. HTTP 429 or other non-200 responses are recorded as source errors.

| Source | Request and credentials | Vendor limit / local cap | Default |
| --- | --- | --- | --- |
| Masto / Mastodon | `GET https://mastodon.social/api/v2/search?q={username}&type=accounts&limit=5`; no token | Mastodon documents default limits of 300 requests per 5 minutes per account and per IP; instance operators can configure limits. This runner sends one query per investigation and emits only exact username matches with `discoverable: true`. | enabled |
| Octosuite public user lookup | `GET https://api.github.com/users/{username}`; no token for public user data | GitHub documents 60 unauthenticated REST requests per hour per originating IP. This runner sends one request per investigation. | enabled |
| OWASP SocialOSINTLM | Not called | The candidate name does not exactly match the current OWASP Social OSINT Agent project. Its official page describes a multi-platform agent using an OpenAI-compatible LLM API; no platform/LLM credentials are supplied by this keyless image. | disabled / deferred |
| scrawler | Not called | Upstream says SCrawler has no CLI, and its FAQ describes cookie/OAuth requirements for supported profile retrieval. This is an interactive, credential-dependent workflow, not a bounded keyless container query. | disabled / deferred |

## Verified source contracts

- Masto 2.0.5 documents `masto -user {username}` and implements a direct request to the Mastodon
  Search API at `mastodon.social`. Its separate cross-instance scan fetches an instance list and
  deliberately finds profiles that opted out of directory listing. This adapter does **not** call
  that scan. It calls one documented Mastodon `GET /api/v2/search` request, limits results to five
  accounts, does not set `resolve` or paginate, and filters out records unless `discoverable` is
  exactly `true`. Only the `mastodon.social` instance is queried. See the [Masto README](https://github.com/C3n7ral051nt4g3ncy/Masto),
  [Masto source](https://github.com/C3n7ral051nt4g3ncy/Masto/blob/master/masto.py#L947-L973),
  [Mastodon Search API](https://docs.joinmastodon.org/methods/search/), and
  [Mastodon rate limits](https://docs.joinmastodon.org/api/rate-limits/).
- Octosuite 5.1.0's documented `User.exists()` path is a public profile lookup at
  `https://api.github.com/users/{username}`. The runner makes only that exact request, adds a
  five-second timeout, disables redirects, validates the returned login, and discards public email,
  biography, and other profile fields. GitHub documents that public user data can be requested
  unauthenticated and sets a 60-request-per-hour unauthenticated REST limit. See the
  [Octosuite README](https://github.com/bellingcat/octosuite),
  [Octosuite GitHub client](https://github.com/bellingcat/octosuite/blob/master/src/octosuite/api/github.py),
  [GitHub Get a user](https://docs.github.com/en/rest/users/users#get-a-user), and
  [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
- The OWASP project name in the candidate list appears to be stale: the current official project is
  [OWASP Social OSINT Agent](https://owasp.github.io/www-project-social-osint-agent/), which documents
  use of OpenAI-compatible LLM APIs and multiple social platforms. It is not queried without the
  required external credentials.
- [SCrawler's official FAQ](https://github.com/AAndyProgram/SCrawler/blob/main/FAQ.md) says it is a
  GUI application and will not have a CLI; it also documents cookies/OAuth for several social
  profile retrieval paths. No GUI or user cookies are used here.

No credentials are stored in the image or repository. The adapter emits only a username, optional
display name, platform label, and canonical public profile URL. A match is a public-source
observation, not proof of account ownership or identity.
