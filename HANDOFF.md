# Aletheia Handoff — Phase 5b Startup

Last updated: 2026-10-11

## Project direction and boundaries

`docs/PROJECT_DIRECTION.md` is the current strategy authority. It describes the grey posture target, max-power dispatch intent, and the hard exclusion of Tier 4 and Tier 5 sources. The current runtime has not implemented all of those target behaviors. Phase 5b and Phase 5c registries are proposals and must be source-checked before integration. Do not ingest plaintext credentials, stolen tokens, leaked databases, or criminal-market content. Do not add paid-only components.

`docs/NOT_INTEGRATED.md` records exclusions and cost corrections. LeakCheck was excluded from Phase 5b by the project owner on 2026-10-11; no integration or lookup was performed.

## Repository snapshot

- Repository: `frostknightfrosty-lgtm/aletheia`; local branch: `main`.
- Local code HEAD before this handoff checkpoint: `78ba2d0f3c9676e388898374e06e1c51b268c3d0`.
- At startup, local `main` was three commits ahead of `origin/main` (`c6f8749a589cf61625dca2e9c248b8e50961a909`) and the worktree was clean. Those local commits contain project-direction documentation and paid-adapter removals; the current local tree has not yet been tested in CI.
- Latest Docker Verification run on remote `main`: run `37864196375`, success, commit `c6f8749a589cf61625dca2e9c248b8e50961a909`, [run URL](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/37864196375). This does not verify the newer local commits.
- Latest Live Investigation workflow run: `37864362862`, failure, same remote commit. Its artifact and failure details have not been inspected in this session; do not infer a cause.
- No Phase 5b additions have been implemented. PhoneInfoga is already present; its scope and metadata need review. No source in this project should be described as verified-live without current CI and raw evidence.

## Verification state

The remote `main` Docker workflow was green at `c6f8749...`; the local tree is ahead and is pending a new push-triggered verification. No local tests were run for the three local commits. The CI run's detailed test summary and artifacts were not independently read in this session. No live OSINT investigation was performed.

Earlier project audits identify these gaps, which remain unaddressed: no verified-live adapters; synthetic fixture provenance; missing egress proxy; file-backed JSON graph/checkpoint stores rather than production backends; incomplete score/confidence separation; no negative-result records; missing required `--purpose`; and no verifiable hash chain. The SQLite benchmark store is separate from graph/checkpoint persistence.

## Current phase and next action

Current phase: Phase 5b, source review and adapter implementation.

Next: push the local commits together with the startup checkpoint and verify that exact tree in CI. Then source-check the remaining Phase 5b candidates in order, beginning with XposedOrNot. Before any implementation, record an authoritative upstream, license/version, endpoint and rate limit, permitted fields, legal tier, and fixture provenance. Use only documentation-backed or authorized fixtures. Confirm PhoneInfoga's existing legal scope rather than creating a duplicate adapter.

The LeakCheck gate is resolved as excluded. Hudson Rock's [official API docs](https://docs.hudsonrock.com/reference/getting-started) require an API-key header and document optional fields that include employee session cookies; establish a free permitted endpoint and a strict non-secret response scope before considering it. Dark-web proposals require an explicit source and response review against the criminal-content exclusion. Do not add or run them if that boundary cannot be established. Lullar and Blackbird also require upstream/package identity, licensing, and maintenance verification.

## Resume protocol notes

Read `RESUME_STATE.json`, `GATES.md`, this file, and the project authority documents before continuing. `RESUME_STATE.json.last_commit` names the latest source/content commit preceding the bookkeeping checkpoint; Git cannot embed the hash of a commit in a file inside that same commit without a self-referential hash. Treat the checkpoint commit as the current repository snapshot and report both SHAs when needed.

No new Phase 8 work has started.

## Deferred issues

- `tests/test_project_manifest.py:99` hardcodes the adapter count (currently 30). Every future adapter addition or removal will break it. A more robust design is to drop the count assertion and only assert that every manifest adapter has a matching fixture file. Defer to a cleanup pass — not blocking.
