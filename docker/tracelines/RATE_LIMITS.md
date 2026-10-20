# tracelines sub-source — source review (`docker/tracelines`)

Upstream: <https://github.com/Prekzursil/tracelines> (AGPL-3.0-or-later).
Pinned commit `99257f0519b30ce7d890db25252f6cf440fa102e` (tag `v0.2.0`,
2026-07-14; PyPI release 0.2.0). The Dockerfile clones the pinned checkout and
installs it unmodified (`pip install --no-deps`), the same isolation pattern
used for the AGPL SearXNG sub-source: this repository ships a driver and an
image definition, not a modified distribution. The build verifies
`git rev-parse HEAD` against the pin, wipes `.git`, and writes the commit to
`/opt/tracelines/PINNED_COMMIT`; the driver reports it in every document.

## What the image runs

`docker/tracelines/run_tracelines.py` (this repository's driver) calls the
pinned package's `extract()` for exactly two providers — **Mapillary** and
**KartaView** — over a small bounding box derived from one point seed. Nothing
else from the package is invoked.

| Driver source | Upstream provider | Requests | Endpoint(s) |
| --- | --- | --- | --- |
| `mapillary` | `MapillaryProvider` | 1 per z14 sequence tile (1–4 for the default 300 m radius) | `GET https://tiles.mapillary.com/maps/vtp/mly1_public/2/14/{x}/{y}?access_token=MLY\|…` — needs the free `MAPILLARY_TOKEN`; without it the provider is recorded as `skipped` |
| `kartaview` | `KartaViewProvider` | 1–2 (two known host candidates) | `GET https://api.openstreetcam.org/2.0/sequence/` or `https://api.kartaview.org/2.0/sequence/?bbTopLeft=…&bbBottomRight=…&itemsPerPage=1000` — keyless |

`--selftest` constructs the provider set, checks the effective settings and
refuses to pass unless **Google is structurally absent** (see below), the
honest user agent is in effect, no upstream SSL-disabling code exists, and the
pure geometry/parse transforms round-trip on synthetic inputs.

## Documented deviations from pinned defaults (all fail closed)

1. **Google is excluded.** The upstream Google provider (`google_sl`) walks
   undocumented internal `streetlevel` coverage tiles; the project's review of
   that path found no permission and Google's terms prohibit scraping/bulk
   extraction of Street View, so the Google provider is not installed
   (`streetlevel` is never installed, the package is installed `--no-deps`, and
   the driver refuses to run when `streetlevel` is importable or when the
   Google provider reports itself available). `nearest`/`historical`/the npm
   client/hosted proxy all depend on the same excluded path and are not
   shipped.
2. **No retries.** Upstream defaults to `max_retries=4` per tile/host; the
   driver sets `max_retries=1` so a block or failure is recorded once, never
   retried.
3. **No cache.** Upstream writes a disk cache (`.svcache`); the driver sets
   `cache_enabled=False` (the disabled cache backend reads and writes nothing).
4. **Honest user agent.** Upstream's default is a placeholder
   (`tracelines/0.1 (research; contact owner)`); the driver sets
   `Aletheia/0.9.0 (tracelines)` and passes it through the only header the
   providers use. Upstream has no TLS-relaxation option (a verified search of
   `tracelines` finds no `ssl`/`verify_ssl` handling); the selftest re-checks
   the pinned sources and fails if such code appears.
5. **Small area.** One point seed becomes a bbox of at most 300 m radius
   (`--radius` is capped); no named areas, no city-sized extraction.

## Deliberately not invoked

| Upstream part | Why not |
| --- | --- |
| `google_sl` provider, `nearest`, `historical` | Undocumented internal Google endpoints; no permission; Street View terms prohibit scraping/bulk extraction; no clean redistribution license. Excluded structurally (dependency not installed; selftest refuses if present). |
| Hosted demo proxy / `npm/` client / Pages GUI / `server/` backend | Thin clients over the shared hosted proxy or self-hosted services; not needed for the local two-provider path. |
| `--snap` (osmnx/geopandas extras) | Pins a heavy optional geospatial stack for road-snapping; the coverage segments themselves do not need it. |
| `--dedupe` | Cross-source deduplication is a presentation choice; the driver reports both sources unfused with provenance (`fuse` with dedupe disabled). |
| Bulk GeoJSON export | The driver summarizes each segment (length, point count, centroid, endpoints) and never writes or redistributes coverage geometry. |

## Data licensing and attribution

- Mapillary data: **CC-BY-SA 4.0** (© Mapillary contributors). The driver keeps
  the source tag and records the attribution string in every finding.
- KartaView data: **CC-BY-SA 4.0** (© KartaView contributors). Same handling.
- The package's own AGPL-3.0-or-later covers the code; the image is operated
  unmodified from the pinned checkout.

## Transport and egress

- aiohttp sessions use the pinned provider defaults (`trust_env` is aiohttp's
  default `False`; the provider constructs its own `ClientSession`), so proxy
  environment variables are **not** read by the upstream providers. The driver
  does not modify this; live runs therefore require the deployment to provide a
  transparent egress path, which is recorded as an open item for the first
  authorized live run (no live run has occurred). This limitation is documented
  rather than bypassed.
- TLS verification is Python/aiohttp's default (verified); upstream contains no
  code that disables it, and the selftest fails if any appears in the pinned
  sources.
- Only the Mapillary tile host and the two KartaView hosts are contacted. The
  point seed is never sent to any other service.

## Rate limits and request budget

- Default radius 300 m: 1–4 Mapillary z14 tiles (one GET each) and at most two
  KartaView sequence GETs. No pagination beyond `itemsPerPage=1000`, no
  retries, no cache.
- A 120 s gather timeout and a 180 s hard deadline bound each invocation.
- Explicit authorization is required for the queried location: the point (and
  the derived bbox) is sent to Mapillary and KartaView.

## Output and failure semantics

- One JSON document on stdout: `source`, `sub_source`, `pinned_commit`,
  `package_version`, `user_agent`, `target`, `bbox`, `requested_sources`,
  `status`, `fused_count`, and per-source entries with `status`
  (`ok`/`empty`/`skipped`/`blocked`/`error`), `reason` where applicable,
  upstream `stats`, and summarized `segments[]`.
- Exit codes: `0` ok/empty/blocked (with a document), `1` error, `2`
  usage/invalid point, `3` hard deadline (180 s watchdog; 120 s gather).
- Blocked responses are recorded once, never retried, challenged, or evaded.
  Classification is honest about what upstream surfaces: KartaView error text
  is scanned for 401/403/429/challenge markers; Mapillary tile failures are
  surfaced only as a count (`tiles_failed`), so they are reported as `error`,
  not as `blocked`.
