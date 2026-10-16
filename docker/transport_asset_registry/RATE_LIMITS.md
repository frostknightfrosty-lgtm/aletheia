# Rate limits, authentication and source review — `transport_asset_registry`

This batch implements the keyless interfaces that have a documented or previously verified bounded request contract. The runner sends at most one request to each applicable source per invocation. It does not download aircraft photos or return FAA registrant names or addresses.

## Implemented sources

| Source | Exact endpoint / request | Authentication | Rate limit / guard | Evidence |
|---|---|---|---|---|
| FAA Aircraft Registration | `GET https://registry.faa.gov/database/ReleasableAircraft.zip` (official daily archive; parse the master CSV locally for an exact N-number) | None | FAA says the archive is refreshed daily and is about 60 MB. One archive download per applicable lookup; responses are capped at 100 MiB. No numeric request quota is published on the download page. | [FAA download page](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download/index.cfm); [FAA master-file field documentation](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/media/ardata.pdf) |
| OpenRailwayMap facility API | `GET https://api.openrailwaymap.org/v2/facility?name=<name>&limit=5` or `...?uic_ref=<uic>&limit=5` | None | One end-user lookup only. Five-second timeout; no retry after HTTP 429. A unique, contact-bearing User-Agent is sent. Bulk queries are not made. The project says API use is intended for small-scale requests and warns that non-public applications may be blocked. | [OpenRailwayMap API README](https://github.com/OpenRailwayMap/OpenRailwayMap-api/blob/master/README.md); [OpenRailwayMap API terms and request conditions](https://wiki.openstreetmap.org/wiki/OpenRailwayMap/API) |
| Planespotters aircraft-photo metadata | `GET https://api.planespotters.net/pub/photos/hex/<hex>` or `GET https://api.planespotters.net/pub/photos/reg/<registration>` | No key (accepted in the recovered verification review; a direct request without credentials returned HTTP 200 JSON on 2026-10-16) | One request for one input identifier. No numeric public quota was found. The runner records photo id, photographer and public detail-page link only; it does not download or retain image bytes. | [Planespotters terms](https://www.planespotters.net/legal/termsofuse?desktop=true); direct endpoint probe on 2026-10-16 (HTTP 200, `application/json`) |

The Planespotters endpoint shape is not described in the currently located vendor documentation. It was already accepted as a keyless endpoint in `docs/VERIFICATION_COMPLETE.md` and was probed again without credentials for this implementation. Treat its request shape as an observed public interface, not a vendor-supported stability guarantee.

## Dropped candidates

| Candidate | Reason not queried | Official evidence |
|---|---|---|
| IMO GISIS / Ship and Company Particulars | IMO documents a public browser search, but no public machine-readable endpoint/API contract was found. The runner does not automate the portal or guess hidden form endpoints. | [IMO public GISIS modules](https://gisis.imo.org/Public/Default.aspx); [IMO note confirming public availability](https://www.imo.org/en/mediacentre/pages/whatsnew-1704.aspx) |
| ERATV | ERA says ERATV migration into the public Knowledge Graph is ongoing; a graph query cannot be represented as verified ERATV records yet. The public UI manual also warns that repeated view/export requests can trigger CAPTCHA, which the runner will not automate or bypass. | [ERA Knowledge Graph coverage status](https://www.era.europa.eu/cs/node/1665); [ERATV public-user manual](https://www.era.europa.eu/system/files/2022-11/eratv_usm_deployment_end-user_support_material_user_manual_nas_en.pdf) |
| ERIS | No official railway asset registry/API matching the name `ERIS` was identified. The current batching plan names ERATV, not ERIS, so no endpoint is inferred from the ambiguous acronym. | [ERA Knowledge Graph / register list](https://www.era.europa.eu/cs/node/1665) |

Each dropped source is returned as a non-querying, auditable skip in the runner output. Its response is synthetic fixture data in tests; no live lookup against a user-provided target occurred during implementation.

## Data minimization

- FAA records are filtered by exact N-number. The runner emits the registration, serial, model code, year, aircraft/engine type, registration status and Mode S fields only. It discards registrant names, addresses, city, state and postal data.
- Planespotters image bytes and thumbnail URLs are not downloaded or included in normalized findings. The record contains only photo identifier, photographer attribution, public detail-page link and queried aircraft identifier.
- OpenRailwayMap results are limited to five facility records, each with a selected set of facility tags, coordinates and OSM identifier.
- `--health` performs no network access and prints `ok` on stdout.
