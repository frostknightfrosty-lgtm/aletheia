# Rate Limits, Authentication and Pins for `geolocation_image`

Every implemented request contract below was checked against the listed source's
own documentation. A missing published numeric limit is recorded as **not
published**. No endpoint, parameter name, provider credential format, or local
CLI option was inferred from a response sample.

## Implemented sub-sources

| Sub-source | Endpoint or local invocation | Auth | Published limit | Format | Official source |
| --- | --- | --- | --- | --- | --- |
| Mapillary Graph API v4 | `GET https://graph.mapillary.com/images?fields=<fields>&bbox=<west,south,east,north>&limit=<limit>` | `Authorization: OAuth <client token>`; Aletheia reads `MAPILLARY_ACCESS_TOKEN` | **not published** | JSON `{data: [...]}` | https://mapillary.github.io/mapillary-python-sdk/docs/mapillary.models/mapillary.models.client/ |
| Nominatim | `GET https://nominatim.openstreetmap.org/search?q=<query>&format=jsonv2&limit=<limit>&addressdetails=1`; reverse uses `lat`, `lon`, `format`, `addressdetails` | none; polite User-Agent | Public service: **1 request/second maximum** | JSON | https://nominatim.org/release-docs/latest/api/Search/, https://nominatim.org/release-docs/latest/api/Reverse/, and https://operations.osmfoundation.org/policies/nominatim/ |
| Copernicus STAC | `GET https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items?bbox=<bbox>&datetime=<datetime>&limit=<limit>` | none for the catalogue metadata search used here; product download is not implemented | **not published** | STAC GeoJSON | https://documentation.dataspace.copernicus.eu/APIs/STAC.html |
| DFIT | `dfit metadata -i <image> -o <report.json>` | local CLI | local CPU; no provider rate | JSON report | https://pypi.org/project/dfit-toolkit/1.0.0/ |
| Steg Analyzer | `steg-analyzer analyze <image> --metadata --ela --histogram --format json --output <directory>` | local CLI | local CPU; no provider rate | JSON report | https://pypi.org/project/steg-analyzer/ |

### Bounded implementation notes

- Mapillary documents a client or user token. `MAPILLARY_ACCESS_TOKEN` is an
  Aletheia configuration name; the vendor documents the `Authorization: OAuth
  <token>` header, not an environment variable. The runner never writes the
  token to stdout, stderr, the endpoint URL, or its JSON result.
- Mapillary and Copernicus require a bounding box. For a
  `geolocation:latitude,longitude[,datetime]` seed, Aletheia derives a bounded
  0.001-degree half-span box. That is input normalization, not a vendor request
  parameter or an assertion about coverage.
- Copernicus runs only when the third geolocation component contains the
  documented STAC `datetime` interval. It searches catalogue metadata only and
  never follows asset links or downloads imagery.
- Nominatim uses a single request and never paginates. Mapillary and
  Copernicus also use at most one request each; all record lists are limited to
  five entries.
- DFIT is pinned at `dfit-toolkit==1.0.0` (MIT, Python >=3.8). The runner calls
  only its documented `metadata` command.
- Steg Analyzer is pinned at `steg-analyzer==1.0.1` (MIT). The runner calls
  only documented metadata, ELA, and histogram analysis options. It does **not**
  run `extract`, `crack`, password, wordlist, or hidden-payload commands. It
  stores only a JSON report hash and top-level key names, never arbitrary
  strings from an image report. Therefore no credential parsing/storage path is
  introduced into the module that handles Mapillary's authenticated request.

## Dropped candidates

| Candidate | Why it is never contacted | Official source reviewed |
| --- | --- | --- |
| PicImageSearch | The package is an aggregator over third-party engines. No one bounded downstream vendor request contract was verified, so the runner does not choose or scrape an undocumented engine. | https://github.com/kitUIN/PicImageSearch |
| tracelines | Its documentation describes deploying the project's own coverage proxy; it fuses Mapillary/KartaView/street-view coverage. This batch neither self-hosts it nor duplicates direct Mapillary. | https://pypi.org/project/tracelines/0.2.0/ |
| ShadowFinder | Needs separate object-height/shadow-length or sun-altitude measurements plus a date/time, which the current single seed cannot represent. | https://github.com/bellingcat/ShadowFinder |
| pybdshadow | Needs a building GeoDataFrame and datetime. Obtaining building geometry would require a separate source already represented by existing mapping adapters. | https://pybdshadow.readthedocs.io/en/stable/ |
| youtube-geofind | Uses YouTube Data API geospatial search; the vendor API is already live in `youtube-api`, so this batch must not query it again. | https://developers.google.com/youtube/v3/docs/search/list |
| GeoLocator | Reviewed implementations require an external panorama index, automatic model/index acquisition, or GPU setup; no bounded pinned single-image contract was found. | https://github.com/Developer-Mike/geolocator |
| Betaface | The product page states the public `betafaceapi.com` service is temporarily down and gives no current detection request contract usable without guessing. | https://www.betaface.com/products.html |

Each dropped candidate is emitted as an explicit `skipped` source in every
runner result. It has no endpoint constant, no network path, and no local
invocation.

## Existing-adapter overlap check

`PROJECT_MANIFEST.json` was checked before implementation. `youtube-geofind`
is an overlap with the existing `youtube-api` vendor path and is dropped.
`tracelines` overlaps the direct Mapillary coverage path and is dropped.
`pybdshadow` would need building geometry already available through existing
mapping work. Nominatim, Mapillary, Copernicus metadata search, DFIT metadata,
and Steg Analyzer's bounded analysis are not implemented by an existing adapter.
