# Rate limits, source scope, and drops — `social_profile`

The image implements two bounded paths: one public search-page request per CrossLinked search engine, and Slinky's local URL parser. It does not log into social networks, access authentication endpoints, rotate proxies, retry challenges, or bypass CAPTCHAs. The normalized output is restricted to `name`, `username`, `email`, `company`, and `source_url`; this implementation emits no generated email, job title, or raw search snippet.

## Implemented sources

| Source | Exact request / operation | Authentication | Rate limit / guard | Evidence |
|---|---|---|---|---|
| CrossLinked 0.3.0 | One first-page GET each to `https://www.google.com/search?q=site:linkedin.com/in+%22<company>%22&num=100&start=0` and `https://www.bing.com/search?q=%22<company>%22+site:linkedin.com/in&first=0`; results parsed with the CrossLinked parser | None | At most two requests total per run, one per engine; five-second timeout; TLS certificate verification on; redirects and retries disabled. No numeric quota is published in the CrossLinked documentation. A challenge or non-200 response is returned as an error and not retried. | [CrossLinked README](https://github.com/m8sec/CrossLinked); [CrossLinked search implementation](https://github.com/m8sec/CrossLinked/blob/master/crosslinked/search.py); [PyPI CrossLinked 0.3.0 and SHA-256](https://pypi.org/project/crosslinked/) |
| Slinky | Local `slinky.Parse(<https-profile-url>)`; no HTTP request | None | No network traffic. Source pinned to commit `e74a138b6bf7264c788871b2e0825455046d09ef`; only supported URLs with type `User` and an HTTPS scheme are emitted. | [Slinky README and parse contract](https://github.com/FurqanSoftware/slinky); [pinned source](https://github.com/FurqanSoftware/slinky/tree/e74a138b6bf7264c788871b2e0825455046d09ef) |

CrossLinked's upstream `search()` method can paginate until its timer expires. This runner intentionally calls the upstream HTML parser with a single first-page response per engine instead; it does not invoke the pagination loop. Search-engine HTML is unstable and can be challenged or changed, so this is a bounded public observation rather than a stable API guarantee.

## Dropped candidates

| Candidate | Reason not queried | Evidence |
|---|---|---|
| Bellingcat TikTok hashtag analysis | Its collector uses TikTokApi and Playwright, automatically retries headed after an error, and relies on browser stealth / pointer simulation in the dependency to avoid bot detection. This adapter does not use that anti-detection path and does not retry or solve a challenge. | [Bellingcat fetch and headed retry](https://github.com/bellingcat/tiktok-hashtag-analysis/blob/main/tiktok_hashtag_analysis/base.py); [TikTokApi session and browser behavior](https://github.com/davidteather/TikTok-Api/blob/main/TikTokApi/tiktok.py) |
| Zehef | Accepts email seeds, mixes account-existence checks with breach/stealer queries, and is not a social-profile query. Its Instagram module posts to an account-creation-attempt endpoint, and its Hudson Rock module handles credential fields; these paths are outside this adapter's input/output scope. | [Zehef README](https://github.com/N0rz3/Zehef/blob/master/README.md); [Instagram account-check module](https://github.com/N0rz3/Zehef/blob/master/modules/accounts/instagram.py); [Hudson Rock module](https://github.com/N0rz3/Zehef/blob/master/modules/breaches/hudsonrock.py) |

The dropped candidates are returned by the runner as non-querying skips and are never invoked.

## Health behavior

`--health` performs no network request, prints exactly `ok` on stdout, and lists implemented/dropped sub-sources on stderr as JSON. It verifies the container can start, not that Google/Bing is reachable or that a real profile was found.
