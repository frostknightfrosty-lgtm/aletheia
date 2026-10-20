# Rate Limits, Authentication and Scope: minecraft

`minecraft` resolves one current Java-edition username through Mojang's public API. It uses no account, token, or credential.

## Endpoints

| Read | Endpoint | Notes |
|---|---|---|
| current profile | `GET https://api.mojang.com/users/profiles/minecraft/{username}` | returns compact UUID + current name; 204/404 means no such profile |
| session profile | `GET https://sessionserver.mojang.com/session/minecraft/profile/{uuid}` | returns the public texture property for the skin/cape |

Reviewed on 2026-10-20. The old `GET https://api.mojang.com/user/profiles/{uuid}/names` endpoint was checked and returns `404 NOT_FOUND`; it is not called. NameMC has no public API and its site terms do not authorize scraping, so it is deliberately excluded.

## Authentication and rate limits

- **No credentials.** Both requests are unauthenticated public GETs with a descriptive `User-Agent` and `Accept: application/json`.
- Two requests per run maximum. 30-second timeout and 1 MB response cap.
- The response header `x-minecraft-rate-limit-result` is recorded as `rate_limit_result` (observed value `UNDER_LIMIT`). A 204/404 is a normal `not_found`; a 401/403/429 is a bounded `error`/`partial`; the adapter never retries, sleeps, rotates proxies, or uses a key.
- Mojang does not publish a numeric quota for this public endpoint in the reviewed documentation. The adapter therefore makes the minimum two calls and does not parallelise.

## Data minimisation

Emitted: current username, compact and dashed UUID, session name, public skin URL, public cape URL (if any), skin model (`slim`/`classic`), and the rate-limit header.

Discarded: the base64 texture property, its signature, texture timestamp, profile actions, and the image bytes themselves. Skin/cape URLs are accepted only from `https://textures.minecraft.net/texture/`; `http` is upgraded to `https` and any other host is dropped.

## Interpretation limits

A Minecraft handle is a same-handle lead, not identity proof. Usernames can be changed and transferred, and Mojang exposes only the current name. The adapter does not fetch NameMC history, so a previous-name trail is unavailable here by design. A UUID identifies the account, not the person. No live target is on file; verification is fixture-based.

## Version pin

Python 3.13 slim container; standard-library-only parser. Descriptor pinned to `1.0 (Mojang public profile API; reviewed 2026-10-20)`.

## Verification

- No live target is on file. `tests/fixtures/minecraft.json` is a synthetic normalized profile using Mojang's documented public fields.
- `--normalize` validates it offline; `--health` and `--selftest` make no network requests. The self-test checks username/UUID grammar, texture decoding, texture-host allowlisting, and normalization.
