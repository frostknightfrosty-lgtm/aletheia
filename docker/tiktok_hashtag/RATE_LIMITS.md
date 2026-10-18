# tiktok-hashtag-analysis sub-source — source review (`docker/tiktok_hashtag`)

Upstream: <https://github.com/bellingcat/tiktok-hashtag-analysis> (MIT).
Version 2.0.4 in the checkout; the project publishes no releases or tags, so
the checkout is pinned by commit
`2a4af674efc4af7c7d592053ec3f475555f37694` (main, 2024-03-11). The Dockerfile
verifies `git rev-parse HEAD` against the pin at build time, wipes `.git`, and
writes the commit to `/opt/tiktok/PINNED_COMMIT`; the driver reports it in
every output document.

## What the image runs

`docker/tiktok_hashtag/run_tiktok_hashtag.py` (this repository's driver)
imports `tiktok_hashtag_analysis.base._fetch_hashtag_data` from the pinned
checkout and calls it directly with `hashtag`, `limit` (default 40), and
`headed=False`:

```python
async def _fetch_hashtag_data(hashtag, limit, headed=False):
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[], num_sessions=1, sleep_after=3, headless=not headed)
        async for video in api.hashtag(name=hashtag).videos(count=limit):
            data.append(video.as_dict)
```

The upstream CLI (`TikTokDownloader.get_hashtag_posts`) retries a failed
download in headed mode. Calling `_fetch_hashtag_data` directly with
`headed=False` makes that retry structurally unreachable; the driver never
launches a headed browser. Nothing is downloaded to disk: the raw video
dictionaries are normalized in memory (id, URL, author handle, create time,
description excerpt, co-hashtag names) and only that sample is printed.

### Stealth patching is disabled (documented deviation)

TikTokApi 6.2.2 calls `stealth_async(page)` unconditionally inside
`create_sessions()`; there is no off switch. Per `docs/LEGAL_MODEL.md`
(evasion tooling is out of bounds), the driver replaces
`TikTokApi.tiktok.stealth_async` with an async no-op before any session is
created and verifies the replacement took effect; the run **fails closed**
if the patch target is missing (it never silently runs with stealth active).
Nothing else about the client is altered. The output document records
`stealth_neutralized: true`.

### Bot detection is reported, not fought

- Empty response, captcha page, or invalid JSON from TikTok is recorded as
  status `blocked` with the exception type and message in `error`; the run
  exits 0 because the honest outcome is "the platform declined", not a
  finding. No challenge is solved, no proxy rotation, no cookie source, no
  `ms_tokens` (the pinned call passes `ms_tokens=[]`).
- The only retry is the pinned client's own bounded tenacity retry
  (`stop_after_attempt(3)`, transient `playwright._impl._errors.Error`
  only), which is inherited with the upstream function.
- The adapter records a `blocked`/`error`/`invalid_hashtag` driver status as
  an explicit `UNKNOWN` marker finding so an empty report is never
  indistinguishable from a real search.

## Deliberately not invoked

| Upstream part | Why not |
| --- | --- |
| `TikTokDownloader` / CLI | Downloads videos (yt-dlp), writes `posts.json` per hashtag, resizes images, writes config; the driver only reads the bounded sample in memory. |
| `download_gallery`, `download_file_and_save` | Media downloads; not needed for hashtag co-occurrence analysis and out of scope. |
| `plot_most_common_hashtags` / seaborn plots | Generates local summary images; the adapter emits structured findings instead. |
| headed mode | See above — structurally unreachable in this driver. |
| cookies / `ms_tokens` / saved sessions | Never supplied; the session is a fresh anonymous browser context. |

## Endpoint inventory (as implemented by the pinned commit)

| Step | Request | Notes |
| --- | --- | --- |
| session creation | `GET https://www.tiktok.com/` (Chromium, headless) | anonymous context; `stealth_async` no-op; the page fetch also harvests the client's default request headers |
| hashtag info | `GET https://www.tiktok.com/api/challenge/detail/?challengeName=<tag>` | resolved once if the hashtag id is not already known |
| hashtag videos | `GET https://www.tiktok.com/api/challenge/item_list/` (`challengeID`, `count`, `cursor`) | one page loop bounded by `count=40`; each item contributes id, author `uniqueId`, `createTime`, `desc`, `textExtra[].hashtagName` |

## Bounds and behavior

- One hashtag per container invocation; one anonymous browser session; a
  bounded post sample (default 40, upstream `videos(count=limit)`).
- The fetch is wrapped in a 180s `asyncio.wait_for` and the whole run in a
  240s hard deadline after which a `deadline_exceeded: true` document is
  printed and the process exits 3.
- Output is one JSON document on stdout: `{source, sub_source, hashtag,
  pinned_commit, checkout_version, stealth_neutralized, requested_limit,
  status, fetched, posts: [{id, url, author, create_time, desc_excerpt,
  cohashtags}], cohashtag_counts, error?}`; status is one of `ok`, `empty`,
  `blocked`, `error`, `invalid_hashtag`.
- `--health` runs offline (import, pin file, stealth target, Chromium
  presence); `--selftest` runs seven offline checks. Both execute under
  `--network none` in CI.
- Egress: the orchestrator passes `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` to
  adapter containers, but headless Chromium does not honor those environment
  variables (the session's API fetches execute inside the browser), and the
  pinned `_fetch_hashtag_data` call path passes no proxy option. Under the
  orchestrator's `--internal` network a live run therefore fails closed (the
  browser has no egress) rather than bypassing the proxy; the Phase 15 policy
  still counts this adapter as wired (`network_required=True`). An explicit
  proxy-capable launch path is a recorded decision item (see
  `docs/PHASE17_RECHECKS.md`, "#4 … live-egress caveat").
- The image pins TikTokApi 6.2.2, playwright 1.42.0, tenacity 8.2.3,
  requests 2.31.0, yt_dlp 2024.3.10, matplotlib 3.8.3, seaborn 0.13.2,
  numpy 1.26.4, and pandas 2.2.1 (the checkout's own `setup.py` imports),
  on Python 3.11 (playwright 1.42.0 has no newer-interpreter wheels).

## Legal position

Public, logged-out hashtag search of platform-suggested posts; no login, no
cookies, no account actions, no media downloads, and no anti-bot evasion —
the dependency's stealth patch is explicitly disabled and a missing patch
target fails the run. Only run against a hashtag with an explicit
authorization assertion (Gate 2) and honor TikTok's terms and rate limits.
Tier 2 in `PROJECT_MANIFEST.json`; the Tier 5 floor is unchanged.
