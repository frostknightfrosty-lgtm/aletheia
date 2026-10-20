# Rate Limits, Authentication and Scope: github_identity

`github_identity` expands one public GitHub handle through five documented REST reads and one public `.keys` read. No token, account, or login is used.

## Endpoints

| Read | Endpoint | Documented contract |
|---|---|---|
| profile | `GET https://api.github.com/users/{username}` | GitHub REST API, API version `2022-11-28` |
| latest repositories | `GET https://api.github.com/users/{username}/repos?per_page=5&sort=updated` | same |
| gists | `GET https://api.github.com/users/{username}/gists?per_page=5` | same |
| public events | `GET https://api.github.com/users/{username}/events/public?per_page=5` | same |
| public SSH keys | `GET https://api.github.com/users/{username}/keys` | same |
| `.keys` text | `GET https://github.com/{username}.keys` | public GitHub web endpoint; one text response, no API token |

Official documentation: <https://docs.github.com/en/rest/users/users>, <https://docs.github.com/en/rest/repos/repos>, <https://docs.github.com/en/rest/gists/gists>, <https://docs.github.com/en/rest/activity/events>, and <https://docs.github.com/en/rest/users/keys>. GitHub's API terms are at <https://docs.github.com/en/site-policy/github-terms/github-terms-of-service> and <https://docs.github.com/en/site-policy/github-terms/github-api-terms>.

## Authentication and rate limit

- **No token.** The adapter sends `User-Agent`, `Accept: application/vnd.github+json`, and `X-GitHub-Api-Version: 2022-11-28`.
- GitHub documents an unauthenticated REST limit of **60 requests per hour per source IP** (<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>). Six requests are made per run, so at most ten runs/hour are possible from one IP before GitHub returns `403`. The runner records `X-RateLimit-Limit`, `Remaining`, `Used`, `Reset`, `Reset-At` and `Resource` and reports a 403 as a bounded partial error; it never retries, sleeps, rotates proxies, or adds a token.
- The `.keys` endpoint is a public text response, not part of the REST quota. It is fetched once per run; a 404 or empty body is treated as "no public keys", not an error.
- GitHub may apply secondary abuse limits. The adapter makes no concurrent requests; the six reads are sequential.

## Data minimisation

Emitted from the profile: login, display name, company, blog, location, bio, public Twitter handle, public repository/gist/follower/following counts, account creation/update times, and HTML URL. The profile `email` field is **explicitly dropped**, as are avatar URLs, Gravatar identifiers, follower/following lists, and all authorization fields.

Emitted from repositories: name, URL, description, language, topics, fork/archive flags, stargazers count, and timestamps. Emitted from gists: ID, URL, description, public flag, file count, and timestamps; gist contents are not fetched. Emitted from events: ID, event type, repository name, and timestamp; the event payload is not fetched.

SSH keys are reduced to the OpenSSH `SHA256:` fingerprint and key type. The key material and any comment are discarded. The same fingerprint from the API and `.keys` is deduplicated and capped at ten.

## Interpretation limits

A GitHub handle is a same-handle lead, not identity proof. Usernames are user-chosen, can be renamed or transferred, and a public key can be shared, rotated, or stale. Repository and event metadata can corroborate a handle, but the adapter does not assert that the account belongs to the person named in an investigation. No live target is on file; verification is fixture-based.

## Version pin

GitHub is a hosted API, so there is no local artefact to pin. The reviewed contract is REST API version `2022-11-28` as documented on 2026-10-20; the image is `python:3.13-slim-bookworm`. The adapter descriptor is pinned at `version_pin="1.0 (GitHub REST API 2022-11-28; reviewed 2026-10-20)"`.

## Verification

- No live target is on file. Verification is fixture-based: a synthetic combined normalized document in `tests/fixtures/github_identity.json`, parser/driver tests, offline self-tests (username grammar, key fingerprinting, email exclusion, dedupe, bounds), and a Docker health smoke under `--network none`.
- The `--normalize` capture case validates a synthetic combined document offline. It performs no network access.
- `--health` performs no network access; it prints exactly `ok` on stdout and a JSON contract summary on stderr.
