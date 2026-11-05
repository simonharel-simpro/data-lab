# data-lab v1 — Implementation Plan (overview)

**Date:** 2026-11-03 · **Repo:** `simonharel-simpro/data-lab` (private) · **Phases:** 5 (2A/2B/2C in parallel)
**Input:** Socratic session + validated Astro spike (`spike-astro/`), simplicity review, resilience and spec-gap passes.

## Goal
A shared base for every data-science project of a solo user (RAG, OCR, ontologies…): one Weaviate (+ vectorizer)
and one MLflow, a shared Python package, a minimal project template, a read-only Astro app that tells each
project's story, a Weavit UI fork attached as a submodule, and a pilot mini-RAG proving it end to end.
Success at 3 months: a new project starts in < 1 h; one MLflow for new runs; a showable static export.

## Phases

| Phase | Title | Files (≈) | Agent | Depends on |
|---|---|---|---|---|
| 1 | Repo foundation, shared infra, fork attached | 12 | general-purpose | — |
| 2A | Shared `datalab` package, template, `datalab-new`, CI | 16 | general-purpose (Python) | 1 |
| 2B | Presentation app (Astro) | 14 | general-purpose (Astro/TS) | 1 |
| 2C | Weavit UI fork: auto-connect to profile `data-lab` | 3 (in fork) | general-purpose (TS/Electron) | 1 |
| 3 | Pilot `mini-rag` (BM25 + vector, DGX LLM) | 12 | general-purpose (Python) | 2A, 2B |

Per-phase specs: `IMPLEMENTATION_PLAN_PHASE_1.md`, `_2A.md`, `_2B.md`, `_2C.md`, `_3.md`.

## Parallel execution rule (2A / 2B / 2C)
`.github/workflows/ci.yml`, `README.md` and `ARCHITECTURE.md` are touched by several phases. Each phase **creates the
file if absent, otherwise appends its own section/job** — never rewrites another phase's part. Phase 1 creates
README.md and ARCHITECTURE.md; `ci.yml` is created by whichever of 2A/2B runs first. Merge order is free.

## Cross-phase contracts (produced by → consumed by)
- **Project name** `NAME_RE = ^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, reserved `{test, datalab, datalab-test, template, y, n, yes, no, on, off, true, false, null}` (the YAML 1.1 bool/null words because PyYAML reads `name: no` as `False` while the JS YAML parser reads `"no"`).
  Identical literal in `packages/datalab/src/datalab/project.py` (2A) and `app/src/lib/name.ts` (2B); both test
  suites read `contracts/name_vectors.json` (created in 1).
- **Project card** `projects/<name>/PROJECT.md`: frontmatter `name` (== folder), `title`, `status`
  (`idée|en cours|conclu|abandonné`), `tags`, `data`, `metric {key, goal: max|min}` + `##` sections. Full schema
  lives once, in the app (2B); Python validates `name` only (2A).
- **MLflow:** experiments named `<name>` or `<name>/<sub>`; every run carries non-overridable tag `project=<name>`
  (2A writes, 2B and 3 read). Env var `DATALAB_MLFLOW_TRACKING_URI`, default `http://127.0.0.1:5050` (both sides).
- **Weaviate:** collections `<Pascal>_<parts>_<hash8>`, hash over `json.dumps([name, *parts])` (2A → 3).
  Ports 127.0.0.1:8090 (HTTP) / 50052 (gRPC); vectorizer module `text2vec-transformers` (1 → 3).
- **Weavit profile** named exactly `data-lab`, HTTP 8090 + gRPC 50052 (README in 1, auto-connect in 2C).
- **Dual-site constants and their guards:** NAME_RE + reserved names → `contracts/name_vectors.json` read by both test
  suites; ports → G-10 parity test (`.env.example` = Python `Settings` = compose) + an app test (`.env.example` =
  `mlflowUri({})`); the fork's `DATALAB_PORTS` (another repo) has no copy-check on purpose: drift fails safe (the
  profile is refused with `skip: ports`, nothing connects to the wrong Weaviate).

## Existing Equivalents

| Mechanism | Existing code (path:line) | Plan |
|---|---|---|
| Weaviate + MLflow compose | `Demo-RAG-crag-dataset/docker-compose.yml` (1.40.2 / v3.17.2, 127.0.0.1, healthchecks) | reuse, distinct ports, add vectorizer |
| Settings | `Demo-RAG-crag-dataset/src/crag_rag/config.py:26-29` | reuse field names, `DATALAB_` prefix |
| Weaviate connect | `Demo-RAG-crag-dataset/src/crag_rag/index.py:178-189` | reuse |
| Collection naming | `Demo-RAG-crag-dataset/src/crag_rag/index.py:47-64` | generalize prefix, hash raw name |
| MLflow preflight / tracked_run | `Demo-RAG-crag-dataset/src/crag_rag/tracking.py:43-81` | reuse, add `project` tag |
| Index ensure (count-checked) | `Demo-RAG-crag-dataset/src/crag_rag/index.py:93-113` | reuse in pilot |
| CRAG-style scoring | `Demo-RAG-crag-dataset/src/crag_rag/evaluation.py` | reuse rules without the judge (pilot) |
| Tooling (ruff, pre-commit, file size) | `Demo-RAG-crag-dataset/pyproject.toml`, `.pre-commit-config.yaml`, `tools/check_file_size.py` | reuse |
| App | `spike-astro/app/src/**` | promote, minus node adapter / LIVE switch |
| Weavit connection profiles | `weavit-ui/src/main/store/store.ts:17,62-68` (persisted); `renderer/src/store.ts:10` (active id in memory) | fork adds auto-connect |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | decision | The app queries the MLflow REST API directly (dev: per request; build: at export); no Python/FastAPI layer | — | — |
| D-2 | decision | Isolation by collection prefix + exact `project` tag; Weaviate multi-tenancy not used in v1 | — | — |
| D-3 | decision | Card schema single-sourced in the app; Python validates `name` only; same NAME_RE both sides | — | — |
| D-4 | decision | Distinct fixed ports 5050 / 8090 / 50052 so Demo-RAG's stack keeps running; env vars prefixed `DATALAB_` | — | — |
| D-5 | cut | Shared vectorizer is English-only in v1: Weaviate module `text2vec-transformers` with `baai-bge-small-en-v1.5-1.13.3` (pinned); French projects get weaker vector search or bring their own vectors | #6 | user, AskUserQuestion 2026-11-03 |
| D-6 | decision | Weavit auto-connects only to the profile named `data-lab`, and only if it is local on 127.0.0.1 with 8090 and 50052 set explicitly (empty ports are refused, never repaired); on failure show the picker, never fall back | — | — |
| D-7 | decision | Pilot in English; correct = token-boundary normalized containment (Demo-RAG `normalize.py`), IDK = missing, `score = accuracy − hallucination` (max) | — | — |
| D-13 | decision | Any invalid card (schema, name ≠ folder, bad metric key) fails the app build with the file named; no "invalid card" UI state | — | — |
| D-14 | decision | Static export shows run names without links and no MLflow URI; links only in dev | — | — |
| D-15 | decision | Pilot runs on a subset of questions log `smoke_*` metrics + tag `smoke=true`, never `score` | — | — |
| D-8 | defer | Cloud deployment of the infra | #1 | — |
| D-9 | defer | [security] Auth + HTTPS on MLflow and Weaviate before any non-local exposure | #2 | — |
| D-10 | defer | Migration of existing projects (Demo-RAG, crag-app, ExpCelineOCR) | #3 | — |
| D-11 | defer | Multi-user, model serving, launching runs from the app | #4 | — |
| D-12 | defer | Periodic rebase of the Weavit fork on upstream | #5 | — |

## Simplicity Review

Before → after: 6 phases → 5 · 11 mechanisms → 7 (reviewer: fable, 2026-11-03)

| # | Action | Class | What | Disposition |
|---|--------|-------|------|-------------|
| S-1 | simplify | mechanism | Weavit already persists profiles; no "default connection" patch | applied (auto-connect kept as user feature, D-6) |
| S-2 | drop | mechanism | `@astrojs/node`, LIVE switch, build:live/start:live | applied (D-1) |
| S-3 | drop | mechanism | vitest → `node --test` (Node 22 strips types) | applied |
| S-4 | drop | mechanism | Makefile → plain `docker compose` with `name: data-lab` | applied |
| S-5 | simplify | mechanism | datalab 5 modules → 3 | applied |
| S-6 | simplify | mechanism | Python validates `name` only | applied (D-3) |
| S-7 | simplify | mechanism | generator = `datalab-new` console script in the package | applied |
| S-8 | keep | mechanism | NAME_RE on both sides, identical literal + shared vectors | applied (D-3) |
| S-9 | add | — | fail when `name` ≠ folder | applied, 2A + 2B |
| S-10 | add | — | exact `tags.project` filter (no prefix collision) | applied, 2B |
| S-11 | add | — | namespaced, exact-name cleanup in integration tests | applied, 2A |
| S-12 | simplify | mechanism | tooling single-sourced (root `ruff.toml`, one env var) | applied |
| S-13 | simplify | mechanism | GitHub Actions in 2A, not 1 | applied |
| S-14 | defer | capability | fork + submodule in v1 → upstream release first | kept by user |
| S-15 | defer | capability | vector run → after BM25 | kept by user |

## Mechanical Rules to Enforce

| Rule | Apply at phase | Recipe match | Scaffold command |
|------|---------------|--------------|------------------|
| Python modules ≤ 200 lines | Phase 1 | `python-fastapi-layered/check_file_length.py` | `/scaffold-linter file-length --recipe python-fastapi-layered/check_file_length.py` |
| Every import is a declared dependency | Phase 2A | `python-fastapi-layered/check_declared_dependencies.py` | `/scaffold-linter declared-deps --recipe python-fastapi-layered/check_declared_dependencies.py` |
| NAME_RE identical on both sides | Phase 2A + 2B | none (contract test over `contracts/name_vectors.json`) | — |
| No secrets committed | Phase 1 | gitleaks pre-commit hook | — |

## CI Gate Surface

| Gate | Laid by | At phase |
|------|---------|----------|
| Hook runner (pre-commit): ruff check/format, gitleaks, file length | Phase 1 (`/init-component` was not run: the plan lays it) | Phase 1 |
| CI-parity workflow (`.github/workflows/ci.yml`: pre-commit + root compose test `uvx pytest tests/` + datalab unit tests) | Phase 2A | Phase 2A |
| Python test + coverage floor ≥ 70 % (`packages/datalab`) | Phase 2A | Phase 2A — first phase with `src/` + tests |
| TS tree: `astro check` + `node --test` with a failing line-coverage floor ≥ 70 % (`--experimental-test-coverage --test-coverage-lines=70`) + `npm run build` (zero projects allowed) | Phase 2B | Phase 2B — new language tree |
| Pilot tree: unit tests in `projects/mini-rag` (own env), `--cov-fail-under=70` | Phase 3 | Phase 3 |
| Fork (TS/Electron): upstream's own `pnpm typecheck && pnpm test` | Phase 2C | Phase 2C (fork repo) |

**Verification at release:** `/loop-implement` Step 10 refuses the final PR until
`recipes/ci/gate-inventory/ci_gate_inventory.py` exits 0; `/plan-validate` refuses READY if this section is missing.

## Failure Modes (resilience)

Trust boundaries crossed: Docker services over HTTP/gRPC · filesystem (cards, template copy) · MLflow REST from
the app · LAN LLM + vectorizer · git submodule · user-edited YAML interpolated into MLflow filters.

| # | Failure mode | Dimension | Required handling | Required test | Phase |
|---|--------------|-----------|-------------------|---------------|-------|
| F-1 | Static export ships a frozen "unavailable" (cold MLflow) | external I/O | self-inflicted → design changed: `/health` warm-up (≤ 30 s polled), one retry, build summary, `DATALAB_STRICT_EXPORT=1` fails the build | `F-1` retry test · `F-1` strict-mode test | 2B |
| F-2 | App reads Demo-RAG's MLflow (port 5000) | config | single constant, `DATALAB_MLFLOW_TRACKING_URI`, default 5050, URI shown in footer | `F-2` default URL · ignores `MLFLOW_URL` | 2B |
| F-3 | Test cleanup deletes a real project | partial failure | reserved names; cleanup by exact created names only | `test_f_3_*` (2) | 2A |
| F-4 | Weaviate split-brain (REST data-lab, gRPC Demo-RAG) | config | compose maps 8090 and 50052; settings defaults; README sets both ports | `test_f_4_compose_maps_distinct_host_ports` · `test_f_4_rest_insert_visible_via_grpc_query` | 1 / 2A |
| F-5 | Runs logged to Demo-RAG via inherited `MLFLOW_TRACKING_URI` | config | self-inflicted → design changed: `env_prefix="DATALAB_"`; preflight sets URI explicitly and logs it | `test_f_5_settings_ignores_bare_mlflow_tracking_uri` | 2A |
| F-6 | Sibling project's runs picked as best | state & data | exact `tags.project` filter; experiments `<name>` or `<name>/…` only | `F-6` sibling test · `test_f_6_*` | 2A / 2B |
| F-7 | Bad `metric.key` reported as "unavailable" | input | schema regex on `metric.key`; `bestRun` re-checks name, returns `invalid-card` | `F-7` (2) | 2B |
| F-8 | `datalab-new` partial copy leaves a stuck folder | partial failure | copy to dot-temp sibling, then `os.rename`; cleanup on error | `test_f_8_failed_copy_leaves_no_project_dir` | 2A |
| F-9 | Template `.venv`/`.env`/lock copied | state | self-inflicted → design changed: copytree ignore list | `test_f_9_new_project_excludes_venv_and_env` | 2A |
| F-10 | Repo root resolved to the submodule | subprocess | self-inflicted → design changed: root found from the package location, no git subprocess | `test_f_10_*` (2) | 2A |
| F-11 | Odd PROJECT.md (CRLF, BOM, empty/list YAML, `name: no`) | input | tolerant split, `utf-8-sig`, dict + str checks, walk-up stops at repo root, one `ProjectError` | `test_f_11_*` (4) | 2A |
| F-12 | NAME_RE drift between sides | contract | shared `contracts/name_vectors.json` | `test_f_12_*` · `F-12` (node) | 2A + 2B |
| F-13 | LLM/vectorizer failure yields a FINISHED run with a lower score | external I/O | config validated up front; timeouts + response shape check; any generation error → FAILED, metrics logged only at the end; count-checked ingest | `test_f_13_*` (3) | 3 |
| F-14 | Auto-connect targets a down/wrong service (incl. blank port → Demo-RAG's 50051, B-2) | external I/O | profile `data-lab` only, local 127.0.0.1 with explicit 8090/50052; failure → existing `error` status + picker; no retry loop | `F-14`, `B-2` (4) | 2C |
| F-15 | Fresh clone / CI: empty `projects/`, missing submodule, tests read `.env` | observability | `projects/.gitkeep`; build with zero projects; README `--recurse-submodules`; conftest clears env | `F-15` (3) | 1 / 2A / 2B |

Each mode above is a phase acceptance criterion — its handling AND its test ship in the named phase.
Unverified: MLflow 3.17 allowed-hosts with 5050→5000 (smoke check in Phase 1); SQLite under concurrent writers
(if "database is locked" appears, switch the backend to Postgres — design change, not handling).

## Unspecified Behaviors (spec-gap)

Decision points: best-run selection · completeness · name validation · collection hashing · project creation ·
auto-connect choice · pilot scoring.

| # | Behavior (was unstated) | Dimension | Decided resolution | Required test | Phase |
|---|-------------------------|-----------|--------------------|---------------|-------|
| U-1 | NaN/±Inf metric as "best" | boundary | keep finite values only; none finite → `no-runs` | `U-1` | 2B |
| U-2 | Names collapsing to one prefix (`mini`, `mini-`) | collision | tightened NAME_RE; raw name in the hash | `test_u_2_*` (2) · `U-2` | 2A, 2B |
| U-3 | Hash ignores part boundaries | collision | `sha256(json.dumps([name, *parts]))[:8]`; parts must be `str` | `test_u_3_*` (2) | 2A |
| U-4 | Names colliding with test/infra namespaces | collision | reserved `{test, datalab, datalab-test, template, y, n, yes, no, on, off, true, false, null}` | `test_u_4_*` (2) | 2A |
| U-5 | Tie on the metric | tie-break | most recent `start_time`, then `run_id` asc | `U-5` | 2B |
| U-6 | Metric logged at several steps | ordering | use the latest value (`run.data.metrics`); documented | `U-6` | 2B |
| U-7 | Experiment naming | scope | `<name>` / `<name>/<sub>`; app keeps exact matches only | `test_u_7_*` · `U-7` | 2A, 2B |
| U-8 | Card without `metric` | defaults | no MLflow call; "pas de métrique" | `U-8` | 2B |
| U-9 | Duplicate / lowercase / comment-only / fenced headings | matching | filled if any occurrence non-empty; exact NFC match; strip HTML comments; ignore fenced blocks | `U-9a..d` | 2B |
| U-10 | `datalab-new` copy and placeholder | defaults | ignore list; token `__DATALAB_PROJECT__`; none left after copy; refuse any existing target | `test_u_10_*` (3) | 2A |
| U-11 | Which Weavit profile auto-connects | precedence | profile named exactly `data-lab`; none → no auto-connect; no fallback (D-6) | `U-11` | 2C |
| U-12 | Pilot answer correctness and IDK | matching | normalized containment; IDK = missing; `score = accuracy − hallucination` (D-7) | `test_u_12_*` (3) | 3 |
| U-13 | Embeddings provider | data model | Weaviate `text2vec-transformers` module (D-5); model id in collection parts | `test_u_13_embedder_id_is_part_of_collection_hash` | 1, 3 |
| U-14 | Re-running the same config | quantity | allowed; tag `config_hash`; U-5 picks the latest | covered by U-5 | 3 |

Added by `/plan-validate` (independent re-derivation, 2026-11-03), each folded into its phase with a test:

| # | Behavior (was unstated) | Decided resolution | Phase |
|---|---|---|---|
| B-1 | Strict export must see the report across Astro module instances | build report on `globalThis` (verified on the spike) | 2B |
| B-2 | Blank Weavit port silently targets Demo-RAG | refuse auto-connect unless 8090/50052 explicit (D-6) | 2C |
| B-3 | Substring scoring counts `50505` as `5050`; "don't" breaks IDK | reuse Demo-RAG token-boundary `normalize`/`contains_phrase` (D-7) | 3 |
| G-4 | Integration test name flaky (`uuid8` may start with a digit) and unreserved | `datalab-test` + `"t" + hex8` | 2A |
| G-6 | A typo in `metric.key` shows as "no runs" | `metric-not-logged` state | 2B |
| G-7 | Raw `--title` breaks YAML | YAML-quoted title | 2A |
| G-8 | Template card not checked against app rules | contract test (idée, missing Objectif) | 3 |
| G-9 | Invalid-card policy, NFD status, BOM/CRLF in app, `name: no` drift | D-13, NFC preprocess, CI fixtures, YAML words reserved | 2B |
| G-10 | Ports in 5 places, untested | parity test `.env.example` = `Settings` = compose | 2A |
| G-12 | Project named like a dependency breaks `uv sync` | template package name `proj-<name>` | 2A |
| D-14/D-15 | Dead links in the static export; smoke runs ranked as best | see Scope Decisions | 2B / 3 |

No `NEEDS-HUMAN` assumption remains open (U-11, U-12, U-13, B-2, G-9, D-14, D-15 decided by the user on 2026-11-03).
