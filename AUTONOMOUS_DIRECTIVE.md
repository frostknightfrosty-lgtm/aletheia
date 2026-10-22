

# AUTONOMOUS DIRECTIVE — Aletheia

**This file is the persistent operating discipline for every AI session that works on Aletheia.** It does not change between sessions. It is the complement to `HANDOFF.md` (current state), `RESUME_STATE.json` (machine-readable resume point), and `GATES.md` (pending decisions).

**Reading order for a new session:**

1. `AUTONOMOUS_DIRECTIVE.md` (this file, at the repo root) and then AGENT_SETUP.md
2. `HANDOFF.md`
3. `RESUME_STATE.json`
4. `GATES.md`
5. `CHANGELOG.md`

If any file is missing or truncated, report the gap before proceeding.

---

## 1. What Aletheia is

Aletheia is a **free, open-source OSINT investigation platform using the Operator-Driven Model recorded in `docs/OPERATOR_DRIVEN_MODEL.md`.** It takes a single seed (username, email, phone, domain, IP, image, name, geolocation, crypto address) and produces a unified, provenance-tracked entity graph across public sources, with resumable investigations, an audit log, and a five-tier descriptive model.

**Stack:** Python 3.13, FastAPI, adapter-plugin architecture, one Docker container per external tool, resumable DAG, hash-chained audit log, unified entity graph. The chain is tamper-evident relative to a preserved run manifest; it is not a digital signature.

**Repo:** `frostknightfrosty-lgtm/aletheia`. Branch `main`. (Earlier `igttm` references are stale.)

**Project goal:** maximum free capability under the Operator-Driven Model. Tiers are descriptive categories for operator awareness, not code-enforced legal gates. The operator assumes full legal responsibility for the data they query and collect. See `docs/OPERATOR_DRIVEN_MODEL.md`; this is not legal advice.

---

## 2. Tier system (descriptive, not enforced)

Every source has a descriptive tier for operator awareness:

| Tier | Category | Meaning |
|---|---|---|
| 1 | Public, unauthenticated, no ToS concern | Lowest operational risk; still subject to law and source terms. |
| 2 | Public, ToS-hostile to automation | The operator accepts the source's terms and any resulting risk. |
| 3 | Requires free API key | Runs when the operator supplies a key. |
| 4 | Leak indexes, aggregators, plaintext credential sources, dark-web indexes, stealer logs | Permitted by project policy; the operator assumes legal and ethical responsibility. |
| 5 | Active network intrusion or malware deployment | Aletheia does not implement these operations; this is a capability boundary, not a code-level legal gate. |

Tiers are descriptive, not enforced by the code. The runtime loader does not block an adapter because of its tier. Aletheia is a passive OSINT platform: it does not perform active network intrusion or malware deployment. Legal responsibility for how the tool is used rests solely with the operator. See `docs/OPERATOR_DRIVEN_MODEL.md`.

---

## 3. Modes — all three always on

There is no mode selector. No `--mode` flag. No `--open` flag. No `--legal-only` flag. Every invocation runs all three mode behaviors simultaneously:

- **Mode 1 (Open) behavior:** every Tier 1 source dispatches. No gating.
- **Mode 2 (Personal) behavior:** the run records a declaration of lawful basis in the audit log. The declaration is optional text; the run does not stop if it is empty.
- **Mode 3 (Sensitive) behavior:** every run produces the full audit trail and fires jurisdiction warning logic. Warning triggers when the seed or any finding suggests a subject in a strong-privacy jurisdiction (GDPR-relevant, minors, health data, protected classes). The warning is informational, not a gate.

The mode concept describes behaviors that always run, not states the operator selects.

---

## 4. Max power by default

An adapter runs whenever its `input_types` matches the seed and its prerequisites (Tier 3 credentials) are met.

- No opt-in flags.
- No per-adapter enable toggles.
- No mode-based gating.
- Every adapter ships with `enabled_by_default: true`.
- An adapter may be registered with `false` only if it carries a `disabled_reason` field. The loader rejects `false` without one.

There is no project-policy tier gate. Tiers are descriptive; every adapter runs when its input types and credentials match. The operator assumes full legal responsibility for the data they query and collect.

---

## 5. Sources not currently integrated

LeakCheck, LeakRadar, OsintCat, OathNet, Blackbird, Lullar, and Hudson Rock are permitted by the Operator-Driven Model but are not integrated. See `docs/NOT_INTEGRATED.md` for previous source-review facts. Their policy status does not mean an adapter is built or verified.

**Paid-only (removed):** twilio-lookup, censys, google-vision.

**ToS-hostile sources:** ONYPHE and similar sources are permitted by the Operator-Driven Model. Their terms remain a risk the operator assumes; lack of an adapter is an implementation fact, not a legal ban.

**Other source-review exclusions:** DarkNyx, osint-darkweb-pkg, Mr.Holmes, IVRE, urlscan, ThreatCluster, Social Analyzer, and ONYPHE remain unimplemented for technical or source-review reasons recorded in `docs/NOT_INTEGRATED.md`. The Operator-Driven Model does not treat ToS hostility as a project-level blocker.

Any new technical or paid-source limitation gets documented in `docs/NOT_INTEGRATED.md` with the specific reason and a primary-source link.

---

## 6. Standing rules (non-negotiable)

These override everything else. Violating any of them invalidates the session.

1. **No fabrication.** Every "green" claim requires a CI run URL. Every "verified" claim requires a commit SHA and a raw artifact line. A claim without evidence is not a claim.
2. **Do not skip, xfail, or delete tests.** Do not weaken assertions to make a test pass.
3. **Do not perform active network intrusion or malware deployment.** Aletheia is a passive OSINT tool. The operator assumes full legal responsibility for the data they query and collect.
4. **Do not add paid-only adapters.** Free-to-register keys are fine. Anything requiring payment to function is not.
5. **Commit state updates separately from code changes.** `RESUME_STATE.json`, `HANDOFF.md`, `CHANGELOG.md` updates get their own commit.
6. **Update `RESUME_STATE.json` after every commit.**
7. **CI artifacts are fetched via `gh` CLI.** Never ask the user to download them manually. If `gh auth` fails, stop and report the exact command and error. Do not retry silently.
8. **Write a handoff at ~75% context usage.** (See §8.)
9. **Surface deferrals in the same message.** If you cannot do something as asked, say so in that same response. Do not silently defer, do not guess, do not fabricate.
10. **Push back on wrong assumptions.** If an instruction or this file contains an error, correct it and note it. Do not silently work around it.

---

## 7. Verification protocol (anti-fabrication)

Every "verified" claim requires all four of:

1. **CI run URL** — not a summary, the actual URL.
2. **Commit SHA** — the exact commit that was tested.
3. **Raw output** — the literal line from the log, or the artifact hash.
4. **A repeat** — the test must have passed in the most recent run, not a prior one.

**Valid claim format:**

```
verified-live: sherlock
Run: https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/37861088776
Commit: 3ecc9d2c14033227d2e1d6aea2bb02a2e0fd574e
Evidence: ci-artifacts/docker-integration/phase1-sherlock.stdout
Raw line: "username:aletheia_test_2026_zz — found"
```

**Invalid claim:** "Sherlock is now verified-live." No URL, no SHA, no raw output.

**If you cannot produce evidence:** say so. "I attempted to verify X but the CI run failed at step Y; here is the failure" is valid. "X is verified" without evidence is not.

**If you fabricate:** stop the project. Report the fabrication to the user immediately. Do not attempt to hide it. Fabrication corrupts the entire project's value, and it is the one failure that cannot be recovered from silently.

---

## 8. Context exhaustion protocol

Context limits are real and expected. Plan for them.

**When you estimate ~75% of your available context is consumed:**

1. Stop starting new tasks.
2. Finish or cleanly abandon the current task.
3. Write `HANDOFF.md` with the full current state (see §9 format).
4. Write `RESUME_STATE.json` with the machine-readable state (see §9 schema).
5. Update `GATES.md` if any gate status changed.
6. Update `CHANGELOG.md` with this session's commits.
7. Verify the repo is in a consistent state: `git status` must be clean; `git log -1` must match `RESUME_STATE.json.last_commit`; the last CI run must match `last_ci_run`.
8. Commit and push all four files.
9. Output the handoff message to the user (see §10).
10. Stop.

**Do not start a new task in the last 25% of context.** A clean handoff is worth more than one more feature.

**Before writing the handoff, verify state integrity.** If `git status` is not clean, or the CI state doesn't match, fix it before writing. A handoff that describes a state the repo is not in is worse than no handoff.

---

## 9. State file formats

### `HANDOFF.md` structure

```markdown
# Aletheia Handoff — <phase/task name>

Last updated: <iso8601>

## Project boundaries
<one paragraph restating the descriptive tier system and operator responsibility>

## Repository and CI state
- Latest CI-verified commit: <sha>
- Docker Verification run <id> <url>: <status>
- Raw artifact summary: <parser preflight / pytest / capture lines>
- <any other recent runs with their raw evidence>

## Phase <N> source-review state
<current phase status, decisions made, reasons>

## Next action
<the exact next thing to do>

## Known deferred issues
<list of things logged but not acted on>

## User-requested pause checkpoint — <date>
<if paused by user, the exact state at pause>
```

### `RESUME_STATE.json` schema

```json
{
  "session_id": "<uuid>",
  "last_updated": "<iso8601>",
  "last_commit": "<sha>",
  "last_ci_run": "<run-id>",
  "last_ci_status": "green | red | running",
  "current_phase": "<number + name>",
  "current_task": "<task within phase>",
  "current_status": "in_progress | blocked | complete",
  "completed_phases": ["<phase>", "..."],
  "pending_phases": ["<phase>", "..."],
  "open_gates": ["<gate number>", "..."],
  "next_action": "<exact next thing to do>",
  "files_in_flight": ["<path>", "..."],
  "notes_for_next_session": "<free text>"
}
```

### `GATES.md` structure

```markdown
# Project Gates

Last reviewed: <iso8601>

## Open gates
<anything currently blocking or pending>

## Resolved gates
<each resolved gate with date, decision, and reason>

## Checks to perform when the task reaches them
<gates not yet reached, with what to verify>
```

---

## 10. Handoff message format

When stopping for context exhaustion, output this exact format to the user:

```
CONTEXT EXHAUSTION HANDOFF

Session: <uuid>
Last commit: <sha>
Last CI run: <id> (<status>)

Completed this session:
<bullet list>

In progress at stop:
<current task>

Next action for the new session:
<exact next step>

Open gates:
<list or "none">

Paste the following into a fresh session:
"Resume Aletheia. Read AUTONOMOUS_DIRECTIVE.md, HANDOFF.md, RESUME_STATE.json, GATES.md, and CHANGELOG.md. Continue from next_action."
```

---

## 11. Execution order and acceptance criteria

Work in this order. Do not reorder without documenting why.

**Phase 5b — remaining adapters**
Acceptance: each adapter has module, Dockerfile, runner, fixture, parser test, Docker integration test, capture case, manifest entry with `legal_tier` and `enabled_by_default: true`. CI green.

**Phase 5c — verify and implement**
Acceptance: every proposal has `verification_status: proposed-unverified` resolved to either `verified` or `rejected`. Verified tools implemented to the same bar as Phase 5b. Rejected tools documented in `NOT_INTEGRATED.md`.

**Audit chain**
Acceptance: real hash chain (each entry contains hash of previous). `aletheia verify-chain <run-id>` command exists. Tamper-detection test exists and passes.

**Storage backends**
Acceptance: Postgres, Neo4j, Elasticsearch, MinIO, Redis backends behind existing `GraphStore`/`CheckpointStore` interfaces. Conformance suite passes against every backend. Migration runner handles version tracking.

**Egress proxy**
Acceptance: implemented per `docs/EGRESS_PROXY_CONTRACT.md`. All adapter traffic forced through it. Per-request logging into audit chain. Rate limiting, kill switch, fail-closed verified in CI.

**Score calibration**
Acceptance: Platt scaling or isotonic regression. `calibrated: true` only where training data exists. Until calibrated, everything stays `score` + `calibrated: false`.

**Batch adapters**
Acceptance: 18 batch adapters implemented. Source registry per sub-check with status, license, rate limit, `enabled_by_default`.

**Live investigation**
Acceptance: one full investigation against an authorized target produces `graph.json`, `report.json`, `report.pdf`, `graph.graphml`, `report.stix2.json`. Chain-of-custody hash recomputes. At least one adapter upgraded `verified-fixture` → `verified-live` with raw evidence attached.

**Documentation and final pass**
Acceptance: README covers install, run, tiers, adapters, exclusions. Every adapter has `legal_notes` and `fixture_provenance`. `PROJECT_MANIFEST.json` matches reality.

---

## 12. Definition of "finished"

The project is finished when **all** of these are true, each backed by raw evidence:

1. Every Phase 5b adapter implemented, tested, CI-green.
2. Every Phase 5c proposal resolved (implemented or rejected with reason).
3. Egress proxy implemented and verified.
4. Storage backends (Postgres, Neo4j, Elasticsearch, MinIO, Redis) behind the interfaces. Conformance suite passes.
5. Audit chain is a real hash chain. `verify-chain` works. Tamper detection tested.
6. Score calibration implemented. `calibrated: true` only where trained.
7. Batch adapters implemented.
8. One live investigation against an authorized target produces a verifiable dossier. Chain-of-custody hash recomputes.
9. Full documentation updated.
10. Full test suite green. **Zero skipped tests that were not skipped at project start.**

Every one of the above requires a CI run URL. A claim without a run URL is not a claim.

---

## 13. Hard gates (the only times to pause and ask)

**Gate 1 — LeakCheck.** RESOLVED. The owner changed the project policy on 2026-10-12: LeakCheck is permitted, not integrated, and no new source implementation is authorized by that classification alone. See `docs/NOT_INTEGRATED.md`.

**Gate 2 — Live investigation target.** Satisfied for `username:frost2233` only by explicit owner assertion. Any other target or broader sweep requires a fresh explicit assertion. Do not use a random public target.

**Gate 3 — Free API keys.** The current Gate 3 set is complete: LeakIX, IPGeolocation, Unpaywall, GrayhatWarfare, AbuseIPDB, Netlas, SauceNAO, YouTube, and abuse.ch keys are configured. Reddit is explicitly excluded by the owner (2026-10-22); `reddit-api` remains a recorded skip and is not a required key. If a required key is absent when a phase needs it, pause and ask; do not stub adapters to bypass credential checks.

Tier labels are descriptive and never a reason to pause for policy uncertainty.

**Additional stop conditions:**
- Three consecutive failures of the same underlying problem.
- A previously-passing test now failing in a way you cannot explain.
- A required upstream tool abandoned, deleted, or moved to a paywall with no free replacement.
- Discovery of a security or privacy issue in the code that could expose user data.

Everything else proceeds autonomously.

---

## 14. Autonomy boundaries

**You may, without asking:**
- Read any file in the repo.
- Write, edit, delete files under `app/`, `tests/`, `docker/`, `ci/`, `docs/`, or repo root.
- Add new adapters, batch adapters, storage backends, tests, docs.
- Write new Dockerfiles.
- Add new CI workflows.
- Commit and push to `main`.
- Trigger CI runs via push or `workflow_dispatch`.
- Read CI artifacts via `gh`.
- Iterate on failures until green.
- Install Python packages locally for testing.

**You may not, without asking:**
- Add active network intrusion or malware deployment. Aletheia is a passive OSINT tool.
- Add a paid-only source.
- Remove a test, weaken an assertion, or skip a case.
- Add a secret or credential to a committed file.
- Force-push or rewrite history.
- Delete a workflow.
- Change the CLI's public interface in a breaking way.
- Add a dependency that requires payment or a commercial license.

---

## 15. Report format

After each phase, output:

```
PHASE <n> — <name>
Status: complete | partial | blocked

Commits:
  <sha> <message>

CI runs:
  <run-id> — <status> — <url>

What changed:
  <bullet list>

Tests:
  Unit:           <passed>/<total>
  Parser:         <passed>/<total>
  Store:          <passed>/<total>
  Docker:         <passed>/<total>
  Integration:    <passed>/<total>

Verified-live adapters:   <count> (was <previous>)
Verified-fixture:         <count> (was <previous>)

Open gates: <list or "none">
Next phase: <name>
```

When blocked:

```
BLOCKED — Gate <n>

Question: <specific question>
What I need: <specific input>
What I did not do: <what is paused>
What I did instead: <what advanced while waiting>
```

When finished:

```
PROJECT COMPLETE

All acceptance criteria met.
<final CI run, final commit, final test count>
Nothing deferred. Nothing fabricated.
```

---

## 16. Style

- No preamble. No "I'll now..." — just do it.
- No summaries of things already said.
- No narration of obvious steps.
- Report only at phase boundaries, gates, and completion.
- If CI takes 45 minutes, wait. Do not start parallel work on a new phase until the previous one is verified green.
- If you find something broken that is out of scope, log it in `HANDOFF.md` under "Deferred issues" and continue. Do not fix it opportunistically.

---

## 17. File maintenance

This directive changes rarely. When it does, the change is a commit of its own with a clear message. Do not edit it opportunistically.

- `AUTONOMOUS_DIRECTIVE.md` — this file, at the repo root. Rarely changes.
- `HANDOFF.md` — updated every session and at every pause.
- `RESUME_STATE.json` — updated every commit.
- `GATES.md` — updated when a gate status changes.
- `CHANGELOG.md` — updated every session.
- `docs/PROJECT_DIRECTION.md` — strategy. Changes when the posture changes.
- `docs/PHASE_5B_REGISTRY.md`, `docs/PHASE_5C_REGISTRY.md`, `docs/NOT_INTEGRATED.md` — updated as adapters move through the pipeline.

---

## 18. What a new session does first

1. Read all files listed in the Reading Order at the top of this document.
2. Confirm the current state: `git log --oneline -5`, `git status`, latest CI run status.
3. Report the state to the user in the phase-report format.
4. Continue from `RESUME_STATE.json.next_action`.
5. Do not wait for confirmation unless you hit a gate.

Go.

