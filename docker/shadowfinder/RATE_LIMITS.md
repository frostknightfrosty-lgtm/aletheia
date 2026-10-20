# ShadowFinder — reviewed scope and limits

Source: <https://github.com/bellingcat/ShadowFinder>
License: MIT (upstream `LICENSE`, Stichting Bellingcat).
Pin: commit `215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8`, tag `v0.7.1`
(released 2026-09-03), operated unmodified in `aletheia/shadowfinder:v1`.

## What the adapter does

One **shadow observation** per invocation: object height (metres), shadow
length (metres), and a UTC datetime. The seed value uses key=value pairs:

```
shadow_observation:height=10;shadow=5;datetime=2024-06-01T12:00:00Z
```

The driver imports the pinned library, loads the `timezone_grid.json` shipped
in the checkout (angular resolution 0.5°), and calls `find_shadows()`. It then
summarises the likelihood grid into ranked 1° bins:

- cells with `|relative_difference| <= tolerance` (default `0.10`, maximum
  `0.50`) are grouped into bins;
- each candidate region reports a bbox, centroid, best cell and cell count;
- at most 20 regions are returned by default (maximum 50);
- `regions_total` and `truncated` record whether the list was cut.

The upstream CLI is not used: it only renders a PNG and regenerates the
timezone grid on first use. Calling the library with the shipped grid avoids
that slow generation step.

## Network and privacy

- **No network calls.** The driver uses no request library; the selftest scans
  the pinned package for outbound-client imports and fails if any is found.
- **No coordinate, measurement, or query leaves the container.** Inputs are
  the observer's measurements; outputs are local computation results.
- No retries, no cache, no telemetry. Matplotlib's config/cache directory is
  `/tmp`, which the runtime mounts as a writable tmpfs.

## Honest limits

- The grid covers **60°S–85°N**; polar regions are not evaluated.
- A 0.5° grid is about 55 km at the equator; 1° bins are coarser. A candidate
  region is a **possibility band from solar geometry**, not a confirmed
  location, not a probability, and not a substitute for corroborating imagery
  or field evidence.
- The model uses the sun's position at the supplied datetime. A wrong clock,
  timezone, or measurement shifts or empties the band.
- Datetimes outside 1900–2100 are rejected. A value without an offset is
  interpreted as UTC.
- Bins are axis-aligned latitude/longitude cells, not connected components;
  two disjoint patches can share a bin.

## Verification

`--health` checks the pin file, package import, the shipped grid, and the
absence of outbound-client imports; it prints exactly `ok` and exits 0.
`--selftest` runs nine checks, including a clipped real computation.
