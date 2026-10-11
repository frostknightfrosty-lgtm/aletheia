# Aletheia Handoff — Phase 5b Source Review

Last updated: 2026-10-11

## Project boundaries

`docs/PROJECT_DIRECTION.md` is the current strategy authority. The Tier 4/5 hard floor remains binding: do not register sources that require consent/warrant, expose plaintext credentials or stolen tokens, ingest leaked databases, or collect criminal-market material. Do not add paid-only default components. The Phase 5b/5c registries are proposals until upstream scope, terms, licensing, and invocation are verified.

LeakCheck is excluded by the project owner. Hudson Rock, DarkNyx, and osint-darkweb-pkg were moved to `docs/NOT_INTEGRATED.md` after source review could not establish the owner's required stable Tier 1–2-only call path. No code was installed, run, or added for those sources.

## Repository and CI state

- Repository: `frostknightfrosty-lgtm/aletheia`, branch `main`.
- Current committed HEAD at the latest CI run: `b74beb866109115b9fc9a312bfdce7110cdbe5c9`.
- Docker Verification run `38167558342` failed on that commit: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38167558342
- Raw artifact lines: `PARSER PREFLIGHT: PASS — 31/31 adapters have parser coverage`; pytest summary `1 failed, 109 passed, 1 warning in 12.51s`; `DOCKER CAPTURE: PASS — 32/32 cases captured`. All 32 `results.json` entries had return code 0, including `phase4-xposedornot`. The sole failure is a stale cumulative Phase 5 registry size in `tests/test_phase5_adapters.py:26` (`assert 26 == 25`); the XposedOrNot parser, Docker image build, and smoke case are covered among the passing checks. No live API lookup has been performed.
- The preceding Docker Verification run `38165531894` succeeded on `cd71a0c5753bd8c94ffea5dc6acb27b093ce50b8`: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38165531894
- The manifest test fix is commit `f68729f7853a1c706232c0c5b39cc08af2773eae`; its CI run `38164845596` also succeeded.
- The XposedOrNot adapter, fixture, and Docker health case passed in run `38167558342`; the overall run is red only because of the stale registry-size assertion described above. No live API lookup has been performed.

## Phase 5b source-review state

- XposedOrNot's official documentation identifies `GET https://api.xposedornot.com/v1/check-email/{email}` as a no-key community endpoint. The safe proposed scope is to omit `details` or set it false, retaining only breach names and the queried email. Documented caps are 25 requests/hour and 100/day per IP. No live call was made because no authorized email target was supplied.
- Hudson Rock was excluded: the official username endpoint searches compromised credentials; documented API use requires an API-key header, and official response examples contain username/password fields. No Boolean-only endpoint was verified.
- DarkNyx was excluded: the free public page searches onion sites, leak dumps, and marketplaces; personal-data masking is explicitly incomplete; the legal terms prohibit scraping; API access is a Pro feature. No public metadata-only endpoint was verified.
- osint-darkweb-pkg was excluded: PyPI sdist `osint_darkweb_pkg-0.1.0.tar.gz`, SHA-256 `7a42152d02d3493ec01e8913964e05b4b850107f9be06f50ba89978795463e42`, was statically inspected only. Its `get_search_results(query)` path requests 17 hardcoded onion engines and returns titles/URLs; separate `scrape_multiple(urls)` fetches onion pages and extracts up to 1200 characters. It has no documented engine allowlist to restrict the public invocation to Ahmia, Torch, and OnionLand. The package was not installed or executed.
- LeakCheck remains excluded by owner decision. See `GATES.md` for resolved gates.
- PhoneInfoga already exists; scope confirmation is still needed before treating the Phase 5b review item as complete.
- Blackbird and Lullar still require source, license, invocation, and maintenance review before any implementation.

## Next action

The test count assertion now needs to reflect the cumulative Phase 5 registry size of 26 after adding XposedOrNot to Phase 4. Change only that expected count, commit, and push; then inspect the push-triggered CI artifact. The XposedOrNot adapter is constrained to the documented no-key `GET https://api.xposedornot.com/v1/check-email/{email}` route with `details` omitted, parsing breach names only. Do not perform a live lookup until the user explicitly supplies and authorizes an email target. Keep all verification claims tied to the exact CI run, commit, and raw artifact evidence.

## Known deferred issues

The broader audit gaps remain: no verified-live adapters, synthetic fixture provenance, no egress proxy, file-backed JSON graph/checkpoint stores, incomplete score/confidence separation, no negative-result records, missing required `--purpose`, and no verifiable audit hash chain. Do not start Phase 8 work until the prescribed earlier phases are complete.

`RESUME_STATE.json` tracks the latest verified commit and CI result. As the state update is committed together with work, its `last_commit` points to the preceding verified commit rather than attempting to embed a self-referential commit hash. Downloaded earlier CI artifact directories remain untracked local evidence and must not be staged with source changes.
