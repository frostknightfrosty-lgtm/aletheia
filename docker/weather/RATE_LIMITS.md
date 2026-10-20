# Rate Limits, Authentication and Scope: weather

`weather` is one bounded adapter over two documented Open-Meteo endpoints. No API key, account, or registration is used.

## Endpoints

| Mode | Endpoint | Query | Data |
|---|---|---|---|
| current forecast | `GET https://api.open-meteo.com/v1/forecast` | `latitude`, `longitude`, `current=temperature_2m,relative_humidity_2m,precipitation,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m`, `timezone=UTC` | current conditions at the nearest model grid point |
| past date | `GET https://archive-api.open-meteo.com/v1/archive` | `latitude`, `longitude`, `start_date=YYYY-MM-DD`, `end_date=YYYY-MM-DD`, `daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,sunrise,sunset`, `timezone=UTC` | one historical day |
| today/future date | `GET https://api.open-meteo.com/v1/forecast` | `latitude`, `longitude`, `start_date=YYYY-MM-DD`, `end_date=YYYY-MM-DD`, `daily=...`, `timezone=UTC` | one forecast day |

Official documentation: <https://open-meteo.com/en/docs> (forecast), <https://open-meteo.com/en/docs/historical-weather-api> (archive).

## Authentication and free-tier terms

- No key or account. Open-Meteo's own terms page (<https://open-meteo.com/en/terms>) states the free API is for **non-commercial use**, with limits of **600 calls per minute, 5,000 per hour and 10,000 per day** per IP/application. Aletheia is a free/open-source, non-commercial project. A downstream commercial deployment must switch to Open-Meteo's paid API; the adapter does not provide that path.
- Data is **CC-BY 4.0**. Every normalized document and finding carries the string `Weather data by Open-Meteo.com (CC-BY 4.0)`. A report that uses the finding must preserve it.
- Open-Meteo's privacy notice says it keeps webserver logs, which may contain coordinates, for 90 days and does not link them to user identities. The adapter sends only coordinates and a date; no seed identity or account data is included.

## Bounds and behavior

- One HTTP request per run; 30-second timeout; 4 MB response cap; no retries, pagination, cache, or proxy rotation.
- A request body is never sent; the coordinate/date is in the query string. No secret exists to leak.
- The response is normalized to a bounded JSON document: grid metadata, units, and at most 31 daily values per field. The adapter never stores the full raw payload.
- `--health` and `--selftest` are offline and perform no network access. `--normalize` validates a saved Open-Meteo response offline.

## Interpretation limits

Weather at the nearest grid point is environmental context. It can corroborate or contradict an image's claimed time/place, but it can never prove that an image was taken at that coordinate or time. Model grid resolution, elevation differences, and forecast error all matter; the document records the returned grid coordinates and elevation so a reader can see the difference from the requested point.

## Version pin

Open-Meteo is a hosted API, so there is no local artefact to pin. The reviewed contract is the Open-Meteo API as documented on 2026-10-20; the image is `python:3.13-slim-bookworm`. The adapter descriptor is pinned at `version_pin="1.0 (Open-Meteo API reviewed 2026-10-20)"`.

## Verification

No live target is on file. Verification is fixture-based: a synthetic normalized forecast document in `tests/fixtures/weather.json`, parser tests, offline driver self-tests, and a Docker health smoke under `--network none`. The `--normalize` capture case uses a synthetic saved API response and performs no network access.
