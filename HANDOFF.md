# Aletheia Handoff — Phase 5c: Gravatar CI-verified, RDAP next

Last updated: 2026-10-11T22:50:47Z

## Project boundaries

`docs/PROJECT_DIRECTION.md` is the current strategy authority. The Tier 4/5 hard floor remains binding: do not register sources that require consent/warrant, expose plaintext credentials or stolen tokens, ingest leaked databases, or collect criminal-market material. Do not add paid-only default components. LeakCheck, Hudson Rock, DarkNyx, osint-darkweb-pkg, Blackbird, Lullar, ONYPHE, Mr.Holmes, IVRE, urlscan, ThreatCluster, and Social Analyzer are excluded (reasons and primary-source links in `docs/NOT_INTEGRATED.md` and `docs/PHASE_5C_REGISTRY.md`). Only Gravatar and RDAP were scoped for Phase 5c implementation. No live lookup has been made against any target.

## Repository and CI state

- Repository: `frostknightfrosty-lgtm/aletheia`, branch `main`.
- Latest CI-verified commit: `200ada277886ee961c90c668bfe4aa36fc5f2899` (`phase-5c: add Gravatar adapter with curated public profile fields`).
- Docker Verification run `38179832021` succeeded on that commit: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38179832021 (`gh run view --json` returned headSha `200ada27…`, conclusion `success`, event `push`).
- Raw artifact lines (downloaded with `gh run download` and read this session): `PARSER PREFLIGHT: PASS — 32/32 adapters have parser coverage` (`ci-parser-preflight.txt`); `119 passed, 1 warning in 12.58s` (`ci-artifacts/pytest-full.log`; no failures, errors, or skips); `DOCKER CAPTURE: PASS — 33/33 cases captured` (`ci-artifacts/docker-integration/capture.log`). `results.json` has 33 entries, 0 nonzero return codes, 33 stdout and 33 stderr files. Case `phase5c-gravatar` ran `docker run --rm --network none aletheia/gravatar:api-v3 --health`, return code 0, stdout `ok`.
- Commits after the verified commit, not CI-verified when this file was written: `597601960d12de8a5427f628c6ca306e7b595457` (manifest: Gravatar `verified-fixture`), `54b85ef06b6f50d3a9156010328ef123f535c769` (gitignore), `fd49ad6e0c0c3475f74b56a2b64b166c34c13926` (state refresh), `131a3f3f38700fba0db8a3702ecdd5fc79eeb224` (`Fix Gravatar manifest note marker to satisfy manifest test`), and the state-file commits that follow. `5976019` wrote `Fixture file:` and fails `tests/test_project_manifest.py::test_verified_fixture_adapter_notes_name_existing_fixture_file` (the marker must be lowercase `fixture file: `); the local manifest test caught it before any push and `131a3f3` fixes it as a new commit (history not amended). The owner instructed a push of all of these right after the state commits. The push-triggered CI run on the pushed head is their verification; this file does not record its result, so read that artifact with `gh`. `origin/main` was at `200ada2` when checked.
- Previous green run: `38172950867` on `ad9676a39cc010a1eafcbb8a4e1001fd9ba5ad87` (31/31 parser, 110 passed, 32/32 capture).
- Commit `593625bde90aed7b1d5b99d84acf4a995f0538b6` has the message `-`. It added `AGENT_SETUP.md`, `AUTONOMOUS_DIRECTIVE.md`, and four `CHANGELOG.md` lines. The message was a formatting slip; it is already on origin, so history is not rewritten.
- The downloaded `ci-artifacts-*/` folders (now including `ci-artifacts-38179832021/`) and `app/aletheia_osint.egg-info/` are ignored via `.gitignore` and remain on disk as local evidence. Never stage them.

### git status snapshot

Taken 2026-10-11T22:50Z, after the manifest and `.gitignore` commits and before this file was rewritten:

```
On branch main
Your branch is ahead of 'origin/main' by 2 commits.

Changes not staged for commit:
	modified:   HANDOFF.md
	modified:   RESUME_STATE.json

Untracked files:
	app/aletheia/adapters/_rdap_draft.py
```

```
54b85ef06b6f50d3a9156010328ef123f535c769 Add egg-info and ci-artifacts-* to gitignore
597601960d12de8a5427f628c6ca306e7b595457 phase-5c: mark Gravatar verified-fixture (CI run 38179832021)
200ada277886ee961c90c668bfe4aa36fc5f2899 phase-5c: add Gravatar adapter with curated public profile fields
593625bde90aed7b1d5b99d84acf4a995f0538b6 -
ad9676a39cc010a1eafcbb8a4e1001fd9ba5ad87 phase-5c: record source scope review
```

The two modified files in that snapshot were the stale 2026-10-11 pause-checkpoint versions that this rewrite replaces.

## Phase 5c source-review state

- Gravatar: implemented in `app/aletheia/adapters/phase5c.py`, wired into `registry.py`, with Dockerfile and runner under `docker/gravatar/`, synthetic fixture `tests/fixtures/gravatar.json`, parser tests in `tests/test_phase5c_adapters.py`, and a manifest entry. Manifest status is `verified-fixture` (synthetic fixture, Docker health smoke only; the local manifest commit is not yet pushed). Scope unchanged: one exact email SHA-256 against `GET https://api.gravatar.com/v3/profiles/{identifier}`, curated public fields only, no identity inference. No live API lookup has occurred.
- RDAP: not implemented and not wired. The only draft is the untracked file `app/aletheia/adapters/_rdap_draft.py`. Its docstring says it was split out of `phase5c.py` on resume. `phase5c.py` now contains only `GravatarAdapter`, so that file is the only copy of the draft and it is not in git history. It was NOT deleted: the project owner's instruction to delete it assumed the RDAP class still lives in `phase5c.py`, which it does not. The owner then retracted the delete instruction (the premise was wrong); do not delete it. Analysis: `git log --all -S RdapAdapter` finds no commit, there is no stash, and no tracked file mentions `RdapAdapter`, so it duplicates nothing. The file was created 2026-10-12 01:13:41, shortly before the Gravatar commit at 01:17. It copies the helpers from `phase5c.py` (`_result` and `_https_url` identical; `_provenance` differs only in confidence 0.99 vs 0.90; `_email_hash` is unused). Its `build_command` runs `python /opt/runner.py ...` and its health check is `python /opt/runner.py --health`, whereas the committed Gravatar pattern relies on the image `ENTRYPOINT ["python", "/opt/runner.py"]` and passes arguments only, so the draft predates or ignores that fix. It does not set `requires_authorization_assertion`. There is no `docker/rdap/`, runner, fixture, test, registry wiring, or manifest entry. The names it imports (`SeedType.DOMAIN/IP`, `EntityType.DOMAIN/IP`) and `Finding.source_kind` exist in `app/aletheia/core/models.py`.
- RDAP scope (from `docs/PHASE_5C_REGISTRY.md`): IANA bootstrap data, one exact `/domain/{domain}` or `/ip/{address}` lookup, standard library only, preserve the registry record URL as provenance, no probing or enumeration.

## Next action

After the owner confirms, implement RDAP as its own bounded increment: decide with the owner what to do with `_rdap_draft.py` (it is the natural starting point), then add the adapter module, registry wiring, Dockerfile and runner, independent synthetic fixture, parser tests, Docker smoke and capture cases, build target, and manifest entry. First read the push-triggered CI artifact for the pushed head and confirm it is green. Verify each increment from the push-triggered workflow artifact before any "verified" claim. Afterward continue the audit-chain phase in the directive order. Do not perform a live XposedOrNot lookup until the user supplies and authorizes an email target.

## Known deferred issues

- Broader audit gaps: no verified-live adapters, synthetic fixture provenance, no egress proxy, file-backed JSON graph/checkpoint stores, incomplete score/confidence separation, no negative-result records, missing required `--purpose`, and no verifiable audit hash chain. Do not start Phase 8 work before the prescribed earlier phases.
- PhoneInfoga parser does not emit Google URLs or OVH Found/range/city fields.
- `_rdap_draft.py` observations (not fixed): an unused `_email_hash` helper, and `ipaddress.ip_address(request.seed.value)` in the IP branch is unguarded against an invalid seed. It is unreviewed and unverified.
- Documentation drift (not fixed): `README.md` status cites run 38168341113 and 110 tests; `PROJECT_MANIFEST.json` `known_environment_limitations` and `validation` still cite 31 Docker cases and an older baseline; `CHANGELOG.md` has duplicated `# Changelog` headers and out-of-order sections; `AGENT_SETUP.md` and the directive refer to `docs/AUTONOMOUS_DIRECTIVE.md` but both live at the repo root.
- `.gitignore` lacks the token patterns `AGENT_SETUP.md` §9 asks to verify (`.aletheia_github_token`, `*.token`); `.env.*` already covers `.env.local`.
- Git warns `LF will be replaced by CRLF` for several files (autocrlf behavior on this Windows checkout). Edit without assuming content changes from line-ending status.
- Tool-environment note: on this machine `git` is not on PATH (use `C:\Program Files\Git\cmd\git.exe` with `-C <repo>`), `docker` is not installed locally, and the tool shell's working directory and aliases do not persist between calls. `gh` is authenticated as `frostknightfrosty-lgtm`. Python 3.14.2 is on PATH (Microsoft Store alias); `pytest` is not on PATH but `python -m pytest` (8.4.2) works. `reportlab` and `rapidfuzz` are not installed, so 5 test modules fail collection locally (`test_phase2_service`, `test_phase4_api`, `test_phase7`, `test_reporting`, `test_resolution`; 102 collected, 5 errors). `python -m pytest tests/test_project_manifest.py -q` runs locally (10 passed after `131a3f3`). Nothing was installed.

## Process note: stale pause checkpoint

The 2026-10-11 pause checkpoint in this file and in `RESUME_STATE.json` became stale. As reported by the project owner, Codex committed the Gravatar work (`200ada2`, 2026-10-12 01:17 +03:00) after the checkpoint was written but before the state files were updated, so the checkpoint kept describing Gravatar as an unfinished draft and named `ad9676a` as the resume point, while HEAD was two commits ahead. Detected on resume 2026-10-12 by comparing `git log` against `RESUME_STATE.json.last_commit`. Rule going forward: after any commit, update `RESUME_STATE.json` and `HANDOFF.md` (in their own commit), and on resume always compare `git log -1` and `git status` to the state files before trusting `next_action`. A second gap, caught this session: the Gravatar manifest note used `Fixture file:` instead of the required `fixture file: ` marker, which would have turned CI red. Run `python -m pytest tests/test_project_manifest.py -q` before committing any manifest edit. `RESUME_STATE.json` now keeps `last_commit` (HEAD just before the state-file commit that wrote it, since a commit cannot embed its own hash) separate from `last_ci_verified_commit` (the latest commit with a green run).

## Pause checkpoint — 2026-10-11 (superseded)

The user paused work on 2026-10-11 because tokens were nearly exhausted, with the Gravatar draft uncommitted. That checkpoint is superseded by this file: the Gravatar work was committed in `200ada2` and CI-verified in run `38179832021`.
