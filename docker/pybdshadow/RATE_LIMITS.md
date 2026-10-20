# pybdshadow — scope, inputs and limits

## Upstream and license

- Upstream: <https://github.com/ni1o1/pybdshadow>
- Pin: commit `e2665ee7a6527b9fb0d581bbf7d6dc2914015b02` (version 0.3.5).
- License: BSD 3-Clause. The package is installed unmodified in its own image;
  the Aletheia driver is separate and does not patch it.
- The package also ships optional footprint-fetching helpers (`get_buildings`)
  and analysis/visualisation modules. This adapter never calls the fetchers and
  the capture runs under `--network none`.

## Input

One local JSON document (`SeedType.FILE_PATH`; any file name — the adapter
checks size and the driver validates the contents) with exactly this shape:

```json
{
  "datetime_utc": "2024-06-01T12:00:00Z",
  "buildings": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {"building_id": "b1", "height": 10.0},
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[0.0, 0.0], [0.0002, 0.0], [0.0002, 0.0002], [0.0, 0.0002], [0.0, 0.0]]]
        }
      }
    ]
  }
}
```

- `datetime_utc` is ISO-8601; a trailing `Z` or an offset is accepted and
  normalised to UTC. A value without an offset is treated as UTC. Years 1900–2100.
- `buildings` is a GeoJSON FeatureCollection with 1–200 Polygon features.
  Each feature needs `properties.height` in metres (0.1–1000) and may set
  `properties.building_id` (1–64 characters, unique; defaults to `b1`, `b2`, …).
- Each exterior ring must be closed, have 4–1000 vertices, and contain one
  linear ring only — holes are rejected because the upstream shadow routine
  uses the exterior ring. Coordinates are WGS84 lon/lat.
- The whole input file is capped at 1,000,000 bytes.

## Bounds and behaviour

- One invocation computes one datetime for the supplied footprints; there is
  no time-range sweep, no retry, no disk cache and no request library call.
- The upstream function computes the sun position at the centre of the
  footprint bounds. If the sun is below the horizon it raises; the driver
  returns `status: "no_sunlight"` and exit code 0 (a valid "no evidence" result,
  not an adapter failure).
- Output is a summary per building: `building_id`, `bbox`, `centroid`,
  `shadow_area_m2` (geodesic, WGS84), `polygons` and `vertices`. Full geometry
  is not returned, so the response stays bounded and does not become a
  redistributable footprint dataset.
- A shadow is geometric evidence for corroboration, not a confirmed location
  and not a probability. It depends on the accuracy of the supplied footprints,
  heights and timestamp.

## Why there is no live run

The source is a local geometry capability: no external target exists, no
network request is made, and the input is owner-supplied. CI exercises the real
library against a synthetic footprint under `--network none`; a live target is
neither required nor authorized.
