# Aletheia Handoff — Phase 5c Source Review Decisions

Last updated: 2026-10-11

## Project boundaries

`docs/PROJECT_DIRECTION.md` is the current strategy authority. The Tier 4/5 hard floor remains binding: do not register sources that require consent/warrant, expose plaintext credentials or stolen tokens, ingest leaked databases, or collect criminal-market material. Do not add paid-only default components. The Phase 5b/5c registries are proposals until upstream scope, terms, licensing, and invocation are verified.

LeakCheck is excluded by the project owner. Hudson Rock, DarkNyx, and osint-darkweb-pkg were reviewed against the owner's exact endpoint conditions and excluded because their documented interfaces do not provide the required stable, enforceable Tier 1–2 scope. Blackbird and Lullar were also excluded: Blackbird has no declared upstream license, and Lullar documents browser-side URL generation with manual profile opening rather than a supported machine interface. No code was installed, run, or added for these sources.

## Repository and CI state

- Repository: `frostknightfrosty-lgtm/aletheia`, branch `main`.
- Latest CI-verified commit: `5a64f428b8479dd497924d9e2c3f3d2acb402eda`.
- Docker Verification run `38172013706` succeeded on that commit: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38172013706
- Raw artifact lines: `PARSER PREFLIGHT: PASS — 31/31 adapters have parser coverage`; `110 passed, 1 warning in 9.71s`; `DOCKER CAPTURE: PASS — 32/32 cases captured`. The artifact's `results.json` contained 32 entries, all with return code 0, with 32 `.stdout` and 32 `.stderr` files. Image build, tests, capture, and artifact upload all succeeded. No live phone scan was performed.
- The XposedOrNot implementation itself was first verified in run `38168341113` on commit `d9b3fe9afc9c7b28be37c8c1a5ae601c481fa59c`, with the same 31/31, 110 passed, and 32/32 evidence.
- Previous run `38167558342` failed on commit `b74beb866109115b9fc9a312bfdce7110cdbe5c9` only because `tests/test_phase5_adapters.py:26` expected 25 cumulative adapters while the registry now contains 26. The one-line expected-count correction is in the green commit above.
- The preceding Docker Verification run `38165531894` succeeded on `cd71a0c5753bd8c94ffea5dc6acb27b093ce50b8`: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38165531894
- The manifest test fix is commit `f68729f7853a1c706232c0c5b39cc08af2773eae`; its CI run `38164845596` also succeeded.
- XposedOrNot is `verified-fixture`; manifest and registry status cite run `38168341113`. Its source remains limited to the documented no-key `GET https://api.xposedornot.com/v1/check-email/{email}` route with `details` omitted, parsing breach names only. No live API lookup has been performed.

## Phase 5b source-review state

- XposedOrNot's official documentation identifies `GET https://api.xposedornot.com/v1/check-email/{email}` as a no-key community endpoint. The safe proposed scope is to omit `details` or set it false, retaining only breach names and the queried email. Documented caps are 25 requests/hour and 100/day per IP. No live call was made because no authorized email target was supplied.
- Hudson Rock was excluded: the official username endpoint searches compromised credentials; documented API use requires an API-key header, and official response examples contain username/password fields. No Boolean-only endpoint was verified.
- DarkNyx was excluded: the free public page searches onion sites, leak dumps, and marketplaces; personal-data masking is explicitly incomplete; the legal terms prohibit scraping; API access is a Pro feature. No public metadata-only endpoint was verified.
- osint-darkweb-pkg was excluded: PyPI sdist `osint_darkweb_pkg-0.1.0.tar.gz`, SHA-256 `7a42152d02d3493ec01e8913964e05b4b850107f9be06f50ba89978795463e42`, was statically inspected only. Its `get_search_results(query)` path requests 17 hardcoded onion engines and returns titles/URLs; separate `scrape_multiple(urls)` fetches onion pages and extracts up to 1200 characters. It has no documented engine allowlist to restrict the public invocation to Ahmia, Torch, and OnionLand. The package was not installed or executed.
- Blackbird's former upstream URL redirects to `antoniaci/blackbird`; repo metadata reports no license and the root has no LICENSE file. Its last push was 2025-07-13. The documented CLI supports `python blackbird.py --username ...`; optional AI and HTML-dump behaviors would not be allowed even if licensing were resolved. No copy was installed or run.
- Lullar's current official checker page says it generates public profile URLs and asks the visitor to open each one to judge whether it exists. It documents no CLI, machine API, or machine-readable results; the landing page's automatic-checking claims conflict with the dedicated checker instructions. No page was queried with a target username.
- LeakCheck remains excluded by owner decision. See `GATES.md` for resolved gates.
- PhoneInfoga v2.11.0 scope is reviewed against official tag-pinned docs/source: `phoneinfoga scan -n <number>` runs local parsing, Google search-link generation without result fetching, and the no-key OVH number-range API. Numverify and Google CSE need credentials; Aletheia does not forward any PhoneInfoga credentials. No live scan was made. Current parser does not emit Google URLs or OVH Found/range/city fields; that is a deferred completeness issue.
- The owner's conditional review requirements for Hudson Rock, DarkNyx, and osint-darkweb-pkg were applied; all three remain excluded because their documented call paths fail the stated conditions. No pending proposal from this group remains active.

## Phase 5c source-review state

- Gravatar and RDAP have narrow public-data scopes documented for implementation. Gravatar will query only the SHA-256 hash of the normalized email via `GET https://api.gravatar.com/v3/profiles/{identifier}` and retain only curated profile fields; it requires an authorization assertion and must not infer identity. RDAP will use the IANA DNS/IPv4/IPv6 bootstrap files for one exact domain or IP lookup, with no probing or enumeration.
- The owner excluded ONYPHE after review of the Free View terms.
- Mr.Holmes, IVRE, urlscan, ThreatCluster, and Social Analyzer were excluded after source/scope review; reasons and primary-source links are in `docs/PHASE_5C_REGISTRY.md` and `docs/NOT_INTEGRATED.md`.
- Proposals without a verified exact upstream remain rejected as recorded in the registry. The proposal list names 19 tools, not 20.

## Next action

Implement the scoped Gravatar adapter and RDAP lookup adapter with independent synthetic fixtures, parser tests, Docker smoke tests, capture cases, build targets, and manifest metadata. Push each bounded increment and verify it in the Docker Verification workflow. Afterward continue the audit-chain phase in the directive order. PhoneInfoga's parser completeness gap remains deferred. Do not perform live XposedOrNot lookups until the user explicitly supplies and authorizes an email target. Keep all verification claims tied to the exact CI run, commit, and raw artifact evidence.

## Known deferred issues

The broader audit gaps remain: no verified-live adapters, synthetic fixture provenance, no egress proxy, file-backed JSON graph/checkpoint stores, incomplete score/confidence separation, no negative-result records, missing required `--purpose`, and no verifiable audit hash chain. Do not start Phase 8 work until the prescribed earlier phases are complete.

`RESUME_STATE.json` tracks the latest verified commit and CI result. As the state update is committed together with work, its `last_commit` points to the preceding verified commit rather than attempting to embed a self-referential commit hash. Downloaded earlier CI artifact directories remain untracked local evidence and must not be staged with source changes.
