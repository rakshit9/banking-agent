# Banking Agent — Project Log

## Project Goal

Build a computer-use automation system for legacy banking applications.

Core architecture:

LLM Discovery → Capability Artifact → Deterministic Replay → Human Handoff

The LLM is used to discover a workflow. Production replay executes the saved capability without LLM decision-making.

## Architecture Decisions

### ADR-001 — LangGraph for discovery orchestration
Status: Accepted

LangGraph coordinates the discovery workflow, bounded exploration steps, compiler-critic refinement loops, and human interruption/resume.

### ADR-002 — Deterministic replay without LLM
Status: Accepted

Saved capabilities must replay without OpenAI making execution decisions.

### ADR-003 — Playwright as current surface driver
Status: Accepted

Playwright is used for the web demo while browser interaction remains abstracted for future desktop/legacy surfaces.

### ADR-004 — Local legacy banking simulator
Status: Accepted

A local fictional banking application provides deterministic success and failure scenarios without real financial data.

### ADR-005 — Artifact Schema / Capability Version Separation
Status: Accepted

Artifact format compatibility (`schema_version: "1.0"`) is explicitly decoupled from individual workflow capability revisions (`version: "1.0.0"`).

### ADR-006 — Multi-strategy Locator Resolution Priority
Status: Accepted

Locators are declared as `LocatorBundle` intent and resolved strictly in semantic order:
1. `role + accessible_name`
2. `label`
3. `stable_attributes`
4. `text`
5. `css`
6. `xpath`
Ambiguous matches (`count > 1`) return `AMBIGUOUS_TARGET` and never silently click arbitrary elements.

### ADR-007 — BrowserController Same-Session Lifecycle
Status: Accepted

`BrowserController` maintains persistent browser context and page references across sequential actions, ensuring cookies (e.g. `verified_M-88888`) and human-handoff state remain intact across transitions.

### ADR-008 — Structured Checkpoint Results and Branch Evaluation
Status: Accepted

Checkpoints evaluate state deterministically (`URL_CONTAINS`, `TEXT_VISIBLE`, `ELEMENT_VISIBLE`, `OUTPUT_PRESENT`, `ONE_OF`) and return structured diagnostics without treating non-fatal business outcomes as system errors.

### ADR-009 — Zero-LLM Deterministic Replay Pipeline
Status: Accepted

`ReplayEngine` executes `CapabilityArtifact` step definitions with 100% deterministic code. No OpenAI client, LLM prompts, or stochastic agents are imported or called during production replay.

### ADR-010 — Pre-Execution Policy Gating & Domain Boundaries
Status: Accepted

`PolicyEngine` runs strictly BEFORE any browser interaction, evaluating action types, step risk levels, and URL/domain whitelists (`ALLOW`, `BLOCK`, `REQUIRE_HUMAN`).

### ADR-011 — Sanitized JSONL Auditing & Visual Evidence Capture
Status: Accepted

`EvidenceRecorder` generates structured JSONL traces per execution (`evidence/replay/<run_id>.jsonl`) and captures screenshots on failures and human checkpoints. `RedactionEngine` masks sensitive parameter values and secrets.

### ADR-012 — Raw Discovery Trace vs. Parameterized CapabilityArtifact
Status: Accepted

Discovery traces contain concrete runtime interactions (e.g. `M-10428`). The `ArtifactCompiler` strictly parameterizes discovery literals into reusable variables (`value_from_input: "member_id"`), and `ArtifactCritic` enforces that no hardcoded scenario IDs leak into registered artifacts.

### ADR-013 — Explicit Control Ownership and Same-Session Handoff Lifecycle
Status: Accepted

Browser control is strictly partitioned between `AUTOMATION` and `HUMAN`. When `HUMAN_REQUIRED` is encountered, automation transitions to `PAUSED`, retaining the live `BrowserController`. The operator claims authority (`HUMAN`), performs manual verification in the same browser context, and triggers resume. Control returns to `AUTOMATION` only after resume checkpoint validation.

### ADR-014 — In-Memory Session Registry and Resume State Validation
Status: Accepted

Active browser sessions are tracked in `HandoffCoordinator` during execution. Resume requests re-observe the live page to verify the obstacle is resolved before advancing replay, preventing invalid state continuation without database/queue overhead for assessment scope.

## Completed

- [x] Project folder structure created
- [x] Demo banking application (FastAPI backend + Jinja2 server-rendered legacy UI)
- [x] Member search flow (Dashboard → Member Search → Member Detail → Savings Account Detail)
- [x] Successful member flow (`M-10428` returning current savings balance `$4,283.42`)
- [x] Member not found scenario (`M-00000` returning stable `Member Not Found` state)
- [x] Permission denied scenario (`M-99999` returning stable `Access Denied` state)
- [x] Manual verification scenario (`M-88888` returning `Additional Verification Required` interstitial + session-persisted continuation)
- [x] Transient slow load scenario (`M-77777` with deterministic 1.0s delay)
- [x] Automated test suite for demo bank (`tests/test_demo_bank.py`, 7 passing tests)
- [x] Shared Pydantic v2 execution models (`backend/core/models.py`)
- [x] Result taxonomy & custom exception hierarchy (`backend/core/errors.py`)
- [x] Versioned CapabilityArtifact schema & YAML/JSON serialization (`backend/core/artifact.py`)
- [x] Semantic LocatorBundle & deterministic resolver (`backend/automation/locators.py`)
- [x] Deterministic CheckpointEvaluator (`backend/automation/checkpoints.py`)
- [x] Persistent-session Playwright BrowserController (`backend/automation/browser.py`)
- [x] Reference capability artifact `member.get_savings_balance` (`artifacts/member_balance_v1.yaml`)
- [x] Automation foundation tests (`tests/test_artifact.py`, 10 passing tests)
- [x] Deterministic PolicyEngine (`backend/core/policy.py`, 8 passing tests)
- [x] Structured EvidenceRecorder & RedactionEngine (`backend/services/evidence.py`)
- [x] Zero-LLM Deterministic ReplayEngine (`backend/automation/replay.py`, 9 passing tests)
- [x] OpenAI computer-use service abstraction (`backend/services/openai_service.py`)
- [x] Explorer Agent (`backend/agents/explorer.py`)
- [x] LangGraph discovery workflow (`backend/agents/graph.py`)
- [x] Artifact Compiler with deterministic parameterization (`backend/agents/compiler.py`)
- [x] Artifact Critic for quality and anti-pattern review (`backend/agents/critic.py`)
- [x] Discovered capability artifact `artifacts/member_balance_discovered_v1.yaml`
- [x] Discovery & generalization test suite (`tests/test_discovery.py`, 7 passing tests)
- [x] Human Handoff Coordinator & control ownership state machine (`backend/core/handoff.py`)
- [x] FastAPI REST endpoints for Capabilities, Discovery, Replay, Run Status, and Interventions (`backend/main.py`)
- [x] Same-session human takeover & resume integration test (`M-88888`)
- [x] Full test suite passing (51/51 tests across all modules)
- [x] Operator frontend scaffolded in `frontend/` as a Next.js + TypeScript app
- [x] Stitch dashboard, discovery, replay, capability inspector, and intervention designs converted into real operator-console routes
- [x] Central typed frontend API client (`frontend/lib/api.ts`) using `NEXT_PUBLIC_API_BASE_URL` with `http://127.0.0.1:8001` development default
- [x] Frontend routes connected to real FastAPI health, capability, discovery, replay, run-status, intervention, take-control, resume, and cancel APIs
- [x] Backend capability selection fixed to prefer artifacts matching configured `DEMO_BANK_URL` when duplicate logical capability IDs exist

## In Progress

- [ ] Assessment Documentation

## Pending

### P0

- [ ] Multi-run stability score benchmark
- [ ] README
- [ ] REPORT

### P1

- [ ] Live execution timeline visualizer

### P2

- [ ] Tenant override demonstration

## Artifact Schema Status

- `schema_version`: `1.0`
- Reference Capability: `member.get_savings_balance` (`artifacts/member_balance_v1.yaml`)
- Discovered Capability: `member.get_savings_balance` (`artifacts/member_balance_discovered_v1.yaml`)
- Parameterization: `member_id` runtime parameter bound to step actions via `value_from_input`

## File Change Log

- `backend/core/handoff.py`: Implemented `ControlOwner`, `RunStatus`, `InterventionStatus`, `HandoffCoordinator`, and in-memory `ActiveSession` registry.
- `backend/main.py`: Implemented FastAPI REST service with endpoints for health, capabilities, background replay, discovery, run inspection, takeover, resume, and cancellation.
- `backend/main.py`: Updated capability lookup to prefer artifacts whose step target URLs match configured `DEMO_BANK_URL`, preventing operator API replay from selecting a test-port discovered artifact.
- `frontend/`: Implemented the final operator console as a minimal Next.js + TypeScript application.
- `frontend/lib/api.ts`: Added typed centralized API access for health, capabilities, discovery, replay, runs, interventions, take-control, resume, and cancel.
- `frontend/components/`: Added shared console layout, status badges, metrics, architecture flow, artifact step rendering, locator/checkpoint viewers, run result, and ownership visualization.
- `frontend/app/`: Added dashboard, discovery studio, capability list/detail, deterministic replay, runs, intervention list/detail routes.
- `tests/test_handoff.py`: Implemented 10 unit and integration tests covering control ownership transitions, invalid state protections, live M-88888 same-session takeover and resume, and FastAPI endpoints.
- `PROJECT_LOG.md`: Updated with Phase 5 architecture decisions, API contracts, test results, and next actions.

## API Contracts

- `GET /api/health`: Health check (`status: ok`)
- `GET /api/capabilities`: List capability summaries
- `GET /api/capabilities/{id}`: Detailed CapabilityArtifact specification
- `POST /api/capabilities/{id}/replay`: Launch background deterministic replay
- `POST /api/discovery`: Launch background AI discovery workflow
- `GET /api/runs/{run_id}`: Sanitized execution run status and outputs
- `GET /api/interventions`: List active/pending human interventions
- `GET /api/interventions/{id}`: Detailed intervention record with screenshot metadata
- `POST /api/interventions/{id}/take-control`: Transfer control authority to `HUMAN`
- `POST /api/interventions/{id}/resume`: Validate safe state and return control to `AUTOMATION`
- `POST /api/interventions/{id}/cancel`: Cancel intervention and terminate run session

## Demo Scenarios & Generalization Verification

- `M-10428 → SUCCESS`: Discovered/replayed flow returning `$4,283.42` (`4283.42`).
- `M-77777 → SUCCESS`: Generalization proof executing `member_balance_discovered_v1.yaml` with zero LLM calls, extracting `$8,910.00` (`8910.00`).
- `M-00000 → MEMBER_NOT_FOUND`: Deterministic `BUSINESS_OUTCOME / MEMBER_NOT_FOUND`.
- `M-99999 → PERMISSION_DENIED`: Deterministic `BUSINESS_OUTCOME / PERMISSION_DENIED`.
- `M-88888 → HUMAN_REQUIRED → HUMAN TAKEOVER → VERIFY → RESUME → SUCCESS`: Full same-session handoff extracting `$5,125.75` (`5125.75`).

## Test Status

- Environment setup: PASS
- Demo bank automated tests (`pytest tests/test_demo_bank.py`): PASS (7/7 tests passing)
- Artifact & Automation foundation tests (`pytest tests/test_artifact.py`): PASS (10/10 tests passing)
- PolicyEngine unit tests (`pytest tests/test_policy.py`): PASS (8/8 tests passing)
- ReplayEngine integration & negative tests (`pytest tests/test_replay.py`): PASS (9/9 tests passing)
- Discovery & Generalization tests (`pytest tests/test_discovery.py`): PASS (7/7 tests passing)
- Human Handoff & FastAPI tests (`pytest tests/test_handoff.py`): PASS (10/10 tests passing)
- Full test suite (`pytest tests/`): PASS (51/51 tests passing)
- Full backend regression after frontend/API integration fix (`python -m pytest tests/` with workspace-local temp): PASS (51/51 tests passing)
- Frontend dependency install (`npm.cmd install --cache .\.npm-cache`): PASS, 0 vulnerabilities after updating to `next@16.3.1`
- Frontend typecheck (`npm.cmd run typecheck`): PASS
- Frontend lint (`npm.cmd run lint`): PASS
- Frontend production build (`npm.cmd run build`): PASS under approved escalation after sandbox EPERM on `tsconfig.json`
- Frontend route smoke test (`/`, `/discovery`, `/capabilities`, `/capabilities/member.get_savings_balance`, `/replay`, `/runs`, `/interventions`): PASS, HTTP 200

## Frontend Operator Console Validation

- Dashboard: PASS, route returns HTTP 200 and calls real backend health/capabilities/interventions APIs.
- Discovery Studio: IMPLEMENTED, starts real `/api/discovery` and polls `/api/runs/{run_id}`; live AI discovery was not manually completed in this validation run.
- Capability Inspector: PASS, route returns HTTP 200 and renders real `CapabilityArtifact` schema, steps, locators, checkpoints, outcomes, safety, and success condition.
- Deterministic Replay: PASS through real backend API.
- `M-10428`: PASS, real replay run `run_cb8272f1` returned `SUCCESS` with `outputs.savings_balance = 4283.42`.
- `M-00000`: PASS, real replay run `run_65b2da0b` returned `BUSINESS_OUTCOME / MEMBER_NOT_FOUND`.
- `M-88888`: PASS to `HUMAN_REQUIRED`, real replay run `run_73afdd20` created intervention `intv_d2a8e747`.
- Take Control: PASS, `POST /api/interventions/intv_d2a8e747/take-control` returned `IN_PROGRESS`, `control_owner = HUMAN`; run moved to `PAUSED`.
- Resume Automation: NOT MANUALLY VALIDATED in this run because no manual verification was completed in the live browser session. Same-session resume remains covered by backend automated tests.

## Stitch Integration Approach

- `stitch-export/` was treated as read-only reference material.
- Preserved the Stitch dark enterprise operations-console language: fixed sidebar, top system indicators, dense cards/tables, status badges, execution timelines, architecture strip, locator/checkpoint panels, and human handoff ownership visualization.
- Replaced Stitch operational mock values with real backend data or honest empty/session-local states.
- Kept static architectural statements such as `Replay = 0 LLM` where they describe the system design rather than runtime metrics.

## Evidence Generated

- `evidence/handoff/`: JSONL audit events (`CONTROL_TRANSFERRED_TO_HUMAN`, `CONTROL_RETURNED_TO_AUTOMATION`, `RUN_SUCCEEDED_AFTER_HANDOFF`).

## Deliberate Cuts

- Distributed session persistence across worker clusters (in-memory `ActiveSession` used for assessment scope).
- Database/ORM layer intentionally omitted to minimize complexity and maximize transparency.

## Next 5 Actions

1. Multi-run stability benchmark.
2. Capture final evidence/screenshots.
3. Complete README.
4. Complete REPORT.
5. Final evaluator rehearsal.

## Last Working State

Command to start demo bank:
```bash
uvicorn demo_bank.app:app --host 127.0.0.1 --port 8000 --reload
```
Command to start Banking Agent backend:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```
Command to start operator frontend:
```bash
cd frontend
npm.cmd run dev
```
Command to run all 51 tests:
```bash
python -m pytest tests/
```

## Session Handoff

### What I completed
- Implemented `HandoffCoordinator` (`backend/core/handoff.py`) with strict `ControlOwner` state machine (`AUTOMATION` -> `PAUSED` -> `HUMAN` -> `RESUMING` -> `AUTOMATION`).
- Built same-session takeover and resume mechanism for `M-88888`, preserving live `BrowserController`, context cookies, and session state.
- Implemented complete FastAPI backend service (`backend/main.py`) exposing health, capability discovery, replay, run status, and intervention control APIs.
- Added comprehensive unit and integration tests (`tests/test_handoff.py`, 10/10 passing).
- Verified full regression test suite: 51/51 passing tests across all modules.
- Updated `PROJECT_LOG.md`.

### What is partially completed
Nothing in Phase 5.

### What is currently broken
Nothing. All 51 unit and integration tests pass cleanly.

### What should be done next
Build the operator dashboard interface, run stability benchmarks, and produce the final assessment report (`REPORT.md`).

### Important context for the next model
During human takeover (`M-88888`), the browser session is kept open in `HandoffCoordinator.active_sessions`. The operator takes control, performs manual verification in the live browser, and calls resume. The coordinator re-evaluates the page state to confirm the security roadblock is cleared before handing control back to `AUTOMATION` and resuming replay to `SUCCESS`.

---

## Final Packaging Update

### Completed
- Created evaluator-facing `README.md` at repository root.
- Added `start-banking-agent.ps1` one-command local launcher.
- Documented architecture, API surface, demo scenarios, setup, evidence-backed validation results, and known limitations.
- Launcher checks existing listeners before starting services, starts missing services with `Start-Process`, redirects logs, and uses bounded health checks.

### Evidence Source of Truth
- AI discovery: `evidence/final/discovery/discovery_result.json`
- Compiled artifact: `artifacts/member_balance_discovered_v1.yaml`
- Replay stability benchmark: `evidence/final/benchmark/benchmark.json`
- Generalization: `evidence/final/benchmark/generalization.json`
- Business outcomes: `evidence/final/benchmark/benchmark.json`
- Slow-load scenario: `evidence/final/benchmark/benchmark.json`

### Validated Claims Captured in README
- Discovery succeeded for `M-10428` and returned `$4283.42`.
- Discovery used `gpt-4o` with 7 model calls.
- Critic approved the compiled artifact with score `0.95`.
- Deterministic replay benchmark completed 10 / 10 successful runs for `M-10428`.
- Replay benchmark used 0 LLM calls.
- Replay median duration was `1.3175` seconds.
- Generalization succeeded for `M-77777`.
- Business outcomes were validated for `M-00000` and `M-99999`.
- Slow-load scenario succeeded for `M-77777`.

### Important Limitation
- Live human handoff was validated through `HUMAN_REQUIRED`, take-control, and paused human ownership. The latest live manual resume was not confirmed in final evidence, so the README does not claim it as a completed live manual validation. Same-session resume behavior remains covered by backend regression tests.

---

## DATASET EXPANSION

### Member Counts
- Members before: 5 total records.
- Normal success members before: 1.
- Members after: 24 total records.
- Normal success members after: 20.

### Newly Added Member IDs
- `M-10214`
- `M-10337`
- `M-10551`
- `M-10672`
- `M-10803`
- `M-10944`
- `M-11026`
- `M-11285`
- `M-11419`
- `M-11563`
- `M-11742`
- `M-11908`
- `M-12031`
- `M-12276`
- `M-12405`
- `M-12648`
- `M-12891`
- `M-13017`
- `M-13254`

### Regression Results
- `python -m pytest tests/test_demo_bank.py`: 7 passed.
- `python -m pytest tests/`: initial run hit Windows temp permission errors for `tmp_path`; rerun with workspace `TMP`/`TEMP` passed 51 / 51.

### Existing Scenario Confirmation
- `M-10428`: success scenario preserved; savings balance remains exactly `4283.42`.
- `M-00000`: `MEMBER_NOT_FOUND` behavior preserved.
- `M-99999`: `PERMISSION_DENIED` behavior preserved.
- `M-88888`: manual verification / `HUMAN_REQUIRED` behavior preserved.
- `M-77777`: slow-load scenario preserved.

### New Member UI Verification
- `M-10214`: Member Search -> Member Detail -> View Savings -> Savings Account Detail returned `$742.18`.
- `M-11563`: Member Search -> Member Detail -> View Savings -> Savings Account Detail returned `$15320.44`.
- `M-13254`: Member Search -> Member Detail -> View Savings -> Savings Account Detail returned `$6875.34`.

### Arbitrary-Member Replay Results
- `M-10214`: expected `742.18`, returned `742.18`, status `SUCCESS`, run `run_8c58478a`.
- `M-11563`: expected `15320.44`, returned `15320.44`, status `SUCCESS`, run `run_8a146aff`.
- `M-13254`: expected `6875.34`, returned `6875.34`, status `SUCCESS`, run `run_527b9522`.
