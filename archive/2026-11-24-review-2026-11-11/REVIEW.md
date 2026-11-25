# Architecture Review — data-lab

**Date:** 2026-11-11
**Project type:** Python (generic) uv monorepo — `packages/datalab`, `projects/mini-rag`, `projects/voice-arch`, `templates/project`, root `tools/` + `tests/` — plus an Astro/TypeScript static dashboard (`app/`) and a Claude Code plugin (`plugins/datalab`, `.claude-plugin/`). `tools/weavit-ui` (external submodule) is out of scope. No `score.yaml` → Simpro Cloud agent skipped.
**Models:** `sonnet` (dimension agents 1–5), `resilience-auditor` (agent 7), CI audit via `/audit-ci --report-only`

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | Medium | 0 | 3 | 5 |
| Typing & Style | High | 0 | 2 | 6 |
| State & Enums | High | 0 | 2 | 8 |
| Testing | Medium | 0 | 10 | 5 |
| Documentation & Debt | Medium | 0 | 3 | 10 |
| Resilience & Failure Modes | Medium | 0 | 4 | 7 |
| CI Gate Surface | Medium | 0 | 5 | 2 |
| Simpro Cloud & AI | N/A | — | — | — |

No critical finding. The codebase is in good shape: the ledger FSM is explicit and fully tested, Python↔TS value sets share one contract with a test on each side, env access is centralised, every subprocess uses list argv, lockfiles and image tags are pinned, and ARCHITECTURE.md / decisions.md are complete and current after the platform split.

### Top Findings (no criticals — the five most impactful warnings)
1. **Lost update on `run.json`** — `write_atomic` has no lock or compare-and-swap; a stale writer silently reverts `produce` (reproduced by the auditor) or a concurrent `eval` loses a test look (`packages/datalab/src/datalab/ledger.py:103-124`).
2. **Unbounded MLflow retries on the read path** — `project_spend`, `stale_runs`, `close_runs` build `MlflowClient` without `_bound_http_retries()` (`tracking_queries.py:76,93,113`); the skill calls them at every resume with no preflight → up to ~20 min hang when MLflow is down.
3. **Voice-arch budget silently under-counted** when the OpenRouter `/key` read fails: FINISHED runs tagged `cost_unknown` add $0 to `spent_so_far`, and the tests pin that as intended (`budget.py:46`, `test_budget.py:84`).
4. **Gate scope holes** — `check_file_size` and `check-function-length` cover `*/src/` only; `tools/pre_commit_checks/check_enum_discipline.py` (202 lines) and `_layout.py::run_layer_check` (31 lines) already escape them; ~30 suppressions carry no justification and nothing lints that.
5. **Cross-project import boundary held by convention only** — no import-linter contract forbids datalab→projects or project→project imports.

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | "datalab must not import projects / projects must not import each other" has no import-linter contract — existing contracts only cover purity (e.g. `name = "booking stays pure"`, `forbidden_modules = ["livekit", "mlflow", "datalab", "httpx"]`). Grep finds no violation today. | `packages/datalab/pyproject.toml`, `projects/mini-rag/pyproject.toml`, `projects/voice-arch/pyproject.toml` | Project isolation | Add `forbidden` contracts (datalab ⊥ `mini_rag`,`voice_arch`; each project ⊥ the other); have the scaffolder emit one for new projects. |
| 🟡 Warning | ARCHITECTURE.md never mentions `contracts/value_sets.json` (`grep -c value_sets ARCHITECTURE.md` → 0), although Python and TS tests both read it. | `ARCHITECTURE.md`, `contracts/value_sets.json` | Layout drift | Add it to the `contracts/` entry with its readers. |
| 🟡 Warning | `tools/pre_commit_checks/check_function_length.py`, `check_declared_dependencies.py`, `_base.py`, `_layout.py` and `.ci-gate-exemptions.json` are absent from the Project Structure block; no hook line for function length. | `ARCHITECTURE.md`, `tools/pre_commit_checks/` | Layout drift | List them; add the function-length hook line. |
| 🔵 Info | Vendored checks use `sys.path.insert(0, str(Path(__file__).parent))` (`check_function_length.py:22`, `check_enum_discipline.py:25`, `check_declared_dependencies.py:26`). | `tools/pre_commit_checks/*.py` | Explicit deps | Acceptable for vendored recipe scripts. |
| 🔵 Info | App: `process.env` is a default argument in `lib/mlflow.ts` (46,156,168,183), `lib/weavit.ts:13`, `integrations/export-guard.ts:26`; `import.meta.env.DEV` read in `Metric.astro:11`, `RunGroups.astro:12`, `Base.astro:8`. Names are centralised in `lib/config.ts` but not zod-validated. | `app/src/lib/*.ts`, `app/src/components/*.astro` | Env in one validated place | Make `config.ts` the sole `process.env` reader; expose one `isDev`. |
| 🔵 Info | Public `dict[str, …]` returns in voice-arch: `worker.py:53` `session_report -> dict[str, object]`, `scoring.py:55` `aggregate -> dict[str, float]`, `fields.py:32` `field_errors -> dict[str, bool]` (others are MLflow param bags / OpenAI schemas). | `projects/voice-arch/src/voice_arch/` | Typed returns | Low priority: TypedDict/dataclass converted at the MLflow boundary. |
| 🔵 Info | voice_arch has ~50 flat modules; layers live only in a doc table + purity contracts. | `projects/voice-arch/src/voice_arch/` | Declared layering | Optional `layers` contract or sub-packages. |
| 🔵 Info | Env access in Python is centralised in pydantic-settings `Settings` (`env_prefix="DATALAB_"`); no scattered `os.getenv`. No catch-all utils, pages are thin (≤42 lines), largest datalab module 197 lines, platform-split modules documented. | — | — | None. |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | Pyright is `basic` outside `src`: root `pyrightconfig.json` `"typeCheckingMode": "basic"` covers `tools`/`tests`; trees use `strict = ["src"]` only. | `pyrightconfig.json`; `packages/datalab/pyproject.toml:84-90` and the 3 other trees | Strict typing | `strict = ["tools"]` at root; consider strict for tests. |
| 🟡 Warning | ruff `select = E,F,W,I,B,UP,S,SIM,RUF,BLE,PLR0913` — no `ANN`, `N`, `T20`, `PGH`, nesting/complexity rules. Annotations are complete today (AST walk: 0 missing) but unenforced. | `ruff.toml:7` | Annotations, naming, no print in library code | Add `ANN`, `N`, `T20`, `PGH003/004`; per-file `T201` ignore for CLI modules. |
| 🔵 Info | `except Exception` in src all justified (log + `exc_info` or re-raise): `voice_arch/call.py:148,152`, `live_caller.py:168`, `worker.py:49`, `tracking_outcome.py:45`, template `train.py:140`/`eval.py:165`. No bare `except:`. | as listed | Specific exceptions | Acceptable isolation boundaries. |
| 🔵 Info | >5-arg functions all carry `# noqa: PLR0913  # <reason> (#39)` (`ledger_ops.py:103`, `generate.py:53` (9), `mini_rag/run.py:87` (9), `index.py:108`, `audio.py:33`, `call.py:156`). | as listed | Max 5 args | Optional config dataclasses for the 9-arg ones. |
| 🔵 Info | `Any` in src: 2 sites, both commented (`ledger_ops.py:28`, `llm_guard.py:33`); test fakes in `mini-rag/tests/test_index*.py` use `-> Any` uncommented. | as listed | No Any without comment | Comment or use `object`. |
| 🔵 Info | `print()` in src is CLI/entry-point output (`ledger.py` main, `new_project.py`, `resources.py`, voice-arch CLIs). `new_project.py:110,112` print inside a helper of the CLI flow. | as listed | No print in library code | None unless reused as a library. |
| 🔵 Info | TS: `app/tsconfig.json` extends `astro/tsconfigs/strict` + `noUncheckedIndexedAccess: true`; eslint `no-explicit-any: error`; 0 `@ts-ignore`/`eslint-disable`/`any`. Components use Astro's `interface Props`. | `app/` | — | None. |
| 🔵 Info | 0 matches: missing annotations, `== None`, wildcard imports, `.format(`, `type(x) ==`; `%` only in lazy logger calls. | — | — | — |

(The unjustified `# type: ignore` finding is consolidated under §5.)

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | Project-card `status` (`idée\|en cours\|conclu\|abandonné`) has no transition map — ARCHITECTURE.md itself says "nothing enforces the transitions". Values repeated in `completeness.ts:5-10`, `projects.ts:4` (typed against `Status`). | `app/src/lib/card.ts:4`, `completeness.ts`, `projects.ts`, `ARCHITECTURE.md:435` | FSM for status fields | Either a `TRANSITIONS` const + git-diff CI check, or an ADR recording the hand-edited-label exemption. |
| 🟡 Warning | Card statuses are not in `contracts/value_sets.json`; only the TS `as const` and ARCHITECTURE.md prose define them. | `contracts/value_sets.json`, `app/src/lib/card.ts:4` | One source for mirrored values | Add `card_statuses` only if Python will ever read card status. |
| 🔵 Info | Ledger FSM compliant: `Status`/`Decision`/`Kind` StrEnums, `TRANSITIONS` (5 rows) enforced at `ledger_ops.py:76`, all Status×Decision pairs tested incl. invalid. | `ledger_model.py:28-53`, `test_ledger_transitions.py` | — | None (see §4 on its oracle). |
| 🔵 Info | Python↔TS ledger values synced through `contracts/value_sets.json` with tests on both sides (`app/src/lib/ledger.test.ts:91-93`, `test_ledger.py:67`). | — | — | None. |
| 🔵 Info | Raw milestone id `"scoping"` at `ledger.py:89` while `DATASET`/`FEATURES`/`MODELING`/`AUDIT` are `Final` constants (`ledger_model.py:20-25`). | `ledger.py:89` | Raw strings | Add `SCOPING: Final`. |
| 🔵 Info | TS: `ledger.ts:158` `entry.status !== 'validated'` raw literal (type-checked against the union). No TS `enum` keyword. | `app/src/lib/ledger.ts:158` | as const | Use a named const. |
| 🔵 Info | Raw strings in tests only (`test_scoring.py:9-31`, `ledger_support.py:38,59`) — intentional serialized-form checks. | tests | — | Optional. |
| 🔵 Info | Other enums in use (`Partition`, `SplitStrategy`, `Retrieval`, `Outcome`, `Goal`, `Tag`, `Region`); 0 project-owned `== "…"` in src; frozen split carried by `split_sha256`, not a status; UI FSM N/A (static site). | — | — | None. |

### 4. Testing Quality

**Test-quality scorecard** (`test_quality_audit.py`; percentages are of active, non-skipped unit tests; env-gated/e2e counted apart)

| Language | Test files | Tests | No-assertion % | Existence-only % | Interaction-only % | Skipped | Env-gated/e2e |
|----------|-----------:|------:|---------------:|-----------------:|-------------------:|--------:|--------------:|
| python | 75 | 679 | 0% | 0% | 0% | 3 | 10 |
| ts | 13 | 120 | 0% | 0% | 0% | 0 | 0 |

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | 1 test skipped, disabled or focused — line(s) 221 | `packages/datalab/tests/test_new_project.py:221` | TQ6 skipped/disabled | fix and re-enable, or delete with a tracked reason |
| 🟡 Warning | 2 tests skipped, disabled or focused — line(s) 154, 166 | `packages/datalab/tests/test_new_project_outside.py:154` | TQ6 skipped/disabled | fix and re-enable, or delete with a tracked reason |
| 🟡 Warning | Scenario catalogue not traceable: `tests/TESTING_SCENARIOS.md` ids (NEW-, DL-, EXP-, PIL-, VA-, APP-) appear in 0 tests; tests use an undefined f/u/g id scheme (`test_f_18_ledger_vectors`, `'U-11: parent with no children…'`). | `tests/TESTING_SCENARIOS.md`, all test dirs | Scenario mapping | Put catalogue ids in test names/docstrings or a map; add a parity test. |
| 🟡 Warning | TQ9: no property-based tests (`hypothesis` absent) for split invariants (`test_split.py:40-62`), voice-arch `normalize` (`test_normalize.py:13-59`), `validate_name`/`package_name` (`project.py:40-60`), ledger decide/redo sequences vs invariants I-1..I-15. | listed | TQ9 | Hypothesis: idempotent normalize, generated disjoint splits always accepted, fuzzed ledger sequences. |
| 🟡 Warning | TQ1: `test_transitions_table_matches_ops` asserts `… .status is TRANSITIONS[(status, decision)]` — oracle imported from the code under test; companion `== 5` magic count. | `packages/datalab/tests/test_ledger_transitions.py:31-63` | TQ1, TQ5 | Literal expected table derived from the spec; set equality instead of `== 5`. |
| 🟡 Warning | TQ3: 42 invalid ledger vectors only assert `str(caught.value).startswith(_expected_prefix(entry["rule"]))` — the blamed milestone/field is never checked. | `packages/datalab/tests/test_ledger.py:42-43` | TQ3 partial | Add a `field`/`message` key to vectors and assert it. |
| 🟡 Warning | TQ5: `assert len(contract["tags"]) == 11` right after a set equality that already covers it. | `packages/datalab/tests/test_tracking.py` (`test_tag_names_match_contract`) | TQ3/TQ5 | Drop the count. |
| 🟡 Warning | TQ3 change detector: `hits = sum(p.read_text(...).count(DATALAB_GIT_URL) …)` / `assert hits == 1` counts the constant in production source; then echoes `DATALAB_GIT_URL == "https://…"`. | `packages/datalab/tests/test_new_project_outside.py:52-56` | TQ3, TQ7 | Assert the scaffolded `pyproject.toml` line only. |
| 🟡 Warning | Missing behaviour: `close_runs` raises `ValueError(f"run {run_id} cannot be read: {err}")` — no test references it. | `packages/datalab/src/datalab/tracking_queries.py:~119` | Missing error path | Test a nonexistent id → `ValueError`, nothing killed. |
| 🟡 Warning | TQ5 roulette: `test_f_9_close_runs_kills_only_given_ids` checks refusal and selective kill in one test, relying on unnamed all-or-nothing behaviour. | `packages/datalab/tests/test_tracking.py:221-231` | TQ5 | Split in two. |
| 🔵 Info | The 3 TQ6 skips are `skipif(sys.platform == "win32", reason="platform-conditional (#8) …")` — tracked and real (sh stub), but leave `uv lock` failure/auth paths untested on Windows. | as above | TQ6 | Optional: `sys.executable`-based Python stub, then close #8. |
| 🔵 Info | Golden vectors (`contracts/run_ledger_vectors.json`, 8 valid / 42 invalid) are a labelled shared contract with the TS app — not circular. | `contracts/run_ledger_vectors.json` | TQ8 | Keep. |
| 🔵 Info | Literal cross-check clean: ports (8090/50052/5050), git URL, provider routing, MLflow 3.17.2 all match live sources. | `compose.yaml`, `settings.py` | — | None. |
| 🔵 Info | TQ2/TQ4 none: module-level test collections are read-only constants; mocks limited to `shutil.which` + owned `uv` stub; tests mirror src one-to-one. | — | — | None. |
| 🔵 Info | `assert "#48" in capsys.readouterr().out` pins an issue number in output text. | `packages/datalab/tests/test_new_project_outside.py:39` | TQ5 | Use a named constant or stable token. |

**Calibration (script tuning, not findings):** false negatives — TQ9 (no property tests, invisible to the scorecard) and TQ1 at `test_ledger_transitions.py:38` (strong-looking assert, production oracle). No false positives.

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | ~30 suppressions without justification, e.g. `# type: ignore[call-arg]` (Settings `_env_file`), `# type: ignore[arg-type]`, `tomllib = None  # type: ignore[assignment]`, `# pyright: ignore[reportUnknownMemberType]`. | `packages/datalab/tests/test_settings.py:114,129`, `test_integration.py:104`; `projects/mini-rag/tests/test_generate.py:50,53`, `test_settings.py:52,59,65,82,132,137`; `projects/voice-arch/src/voice_arch/{live_caller.py:54,llm_guard.py:50,sweep.py:106,worker.py:58}`; voice-arch tests; `templates/project/tests/test_eval.py:218`; `tools/pre_commit_checks/_layout.py:35,61,95`, `check_declared_dependencies.py:33,40` | Suppressions need a WHY | Add reasons; a typed `make_settings(**kw)` test helper removes ~15; lint with ruff `PGH003/004` or a grep hook. |
| 🟡 Warning | `check_file_size` scope is `^(packages\|projects\|templates)/[^/]+/src/.*\.py$` and counts physical lines; it misses `tools/` (`check_enum_discipline.py` 202 lines), root `tests/` (`test_plugin.py` 225), 17 tree test files >200 (`test_project.py` 280, …) and `.ts/.astro/.sh`. | `tools/check_file_size.py`, `.pre-commit-config.yaml:22-24` | Hotspot files | Extend to `tools/` (and decide explicitly about tests); split `check_enum_discipline.py`. |
| 🟡 Warning | Function length: `tools/pre_commit_checks/_layout.py::run_layer_check` 31 lines; test helpers `test_index.py::get` 41, `test_index_concurrency.py::get` 36. The hook covers `src/` only. | listed | Functions ≤30 lines | Split `run_layer_check`; widen hook or accept test helpers explicitly. |
| 🔵 Info | Dev deps use `>=` without upper bound (`pytest>=8`, `pyright>=1.1.390`, …) — covered by ADR 2026-11-09 (`uv.lock` + `uv sync --locked`). | `packages/datalab/pyproject.toml:19-24`, `projects/mini-rag/pyproject.toml:18-24` | Pinning (note) | Optionally align with exact pins used elsewhere. |
| 🔵 Info | `hydra-core==1.3.8` / `omegaconf==2.3.1` not justified in Tech Stack. | `ARCHITECTURE.md:164`, `templates/project/pyproject.toml:7` | Dependency justification | Add a Tech Stack bullet. |
| 🔵 Info | Shipped platform plans still at root (`IMPLEMENTATION_PLAN_PLATFORM*.md`, `IMPLEMENTATION_NOTES.md`, `IMPLEMENTATION_STATUS.md`); ADRs link the phase files. | repo root | Doc hygiene | `/plan-archive`, update ADR links. |
| 🔵 Info | ARCHITECTURE.md has all 7 sections and matches the code (platform split included). | `ARCHITECTURE.md` | — | None. |
| 🔵 Info | decisions.md: 28 ADRs, consistent format. | `decisions.md` | — | None. |
| 🔵 Info | README commands/paths spot-checked accurate (`datalab.toml`, git bootstrap, marketplace, `/datalab:experiment`). | `README.md` | — | None. |
| 🔵 Info | Security: 0 `shell=True`/`os.system`/`yaml.load(`/f-string SQL; secret-like literals are test fixtures; `.env` untracked; subprocess list argv with `# noqa: S603  # fixed argv`. | — | — | None. |
| 🔵 Info | 0 TODO/FIXME/HACK (hits are `Status.TODO`). | — | — | None. |
| 🔵 Info | Lockfiles committed (3× `uv.lock`, `app/package-lock.json`); images pinned by tag (weaviate 1.40.2, mlflow v3.17.2, …). | `compose.yaml` | — | Digest pins optional. |
| 🔵 Info | App: no `@ts-ignore`, no `<img>`, errors stringified (`ledger.ts:121`); no catch-all utils. | — | — | None. |

### 6. Resilience & Failure Modes

| Severity | Finding | File(s) | Dimension | Status | Already tested? | Proposed test |
|----------|---------|---------|-----------|--------|-----------------|---------------|
| 🟡 Warning | Read-side MLflow helpers never bound HTTP retries: `project_spend`, `stale_runs`, `close_runs` build `MlflowClient(tracking_uri=…)` without `_bound_http_retries()`; skill calls them with no preflight; `voice_arch.decide.main` has none either. | `packages/datalab/src/datalab/tracking_queries.py:76,93,113`, `tracking.py:65-68`, `projects/voice-arch/src/voice_arch/decide.py:112` | 1 external I/O | CONFIRMED (hang length SUSPECTED) | No | `test_query_helpers_bound_mlflow_http_retries` (parametrised) + `test_decide_unreachable_mlflow_fails_fast` |
| 🟡 Warning | Lost update on `run.json`: no lock/CAS in `write_atomic`; `_check_overwrite` only guards `decisions_log`, `test_looks`, `kind`. Stale write reverts `produce` / nulls `split_sha256` (reproduced); concurrent template `eval` runs can lose a test look. | `packages/datalab/src/datalab/ledger.py:78-124`, `templates/project/src/__DATALAB_PACKAGE__/eval.py:77,142` | 3 concurrency | CONFIRMED | No | `test_stale_write_does_not_revert_produce`, `test_concurrent_test_look_is_never_lost`; fix with a lockfile or CAS on bytes read |
| 🟡 Warning | Voice-arch budget under-counted when OpenRouter `/key` read fails: `_before=None` → only `cost_unknown` tag, no ceiling, FINISHED run adds $0. Tests pin it as intended. | `projects/voice-arch/src/voice_arch/openrouter_key.py:78-83`, `sweep.py:80-82`, `budget.py:46` | 10 observability / money | CONFIRMED | Pinned as intended (`test_budget.py:84`, `test_runner.py:206`) | `test_finished_run_tagged_cost_unknown_counts_at_estimate` replacing `test_budget.py:84` |
| 🟡 Warning | Raw-bytes hashes (`split_sha256`, data hash) with no `.gitattributes`: a Windows `core.autocrlf=true` clone fails V-2 with a misleading tamper message. | `packages/datalab/src/datalab/split.py:150-151`, `ledger_ops.py:165-175`, `ledger_access.py:16-17` | 6 cross-platform | CONFIRMED mechanism, trigger SUSPECTED | No | `test_gitattributes_pins_hashed_files`, `test_crlf_split_mismatch_names_line_endings` |
| 🔵 Info | `close_runs` not retry-safe after partial failure (already-KILLED ids then refused). | `tracking_queries.py:111-123` | 4 partial failure | CONFIRMED | No | `test_close_runs_retry_after_partial_failure` |
| 🔵 Info | Eval look spent without a persisted score if `mlflow.log_metric` fails. | `templates/project/src/__DATALAB_PACKAGE__/eval.py:140-148` | 4 partial failure | CONFIRMED | No | `test_eval_score_survives_mlflow_failure_after_look` |
| 🔵 Info | `_fsync_dir` after `os.replace` in the same `try` → error reported after commit. | `packages/datalab/src/datalab/ledger.py:103-114` | 4 partial failure | CONFIRMED | No | `test_dir_fsync_failure_after_replace_is_reported_as_committed` |
| 🔵 Info | `datalab-new` leaves `projects/.<name>.tmp-xxxx` on Ctrl-C (handler catches `OSError`/`ProjectError` only). | `packages/datalab/src/datalab/new_project.py:152-158` | 4 partial failure | CONFIRMED | No | `test_interrupt_during_lock_leaves_no_tmp_dir` |
| 🔵 Info | `wiring.apply`: fixed tmp name, no cleanup; `write_text` without `newline="\n"`; partial apply not re-runnable. | `packages/datalab/src/datalab/wiring.py:174-178`, `new_project.py:59` | 4 / 6 | CONFIRMED | Partly | `test_apply_failure_leaves_no_tmp`, `test_apply_writes_lf` |
| 🔵 Info | `_AUTH_FAILURE` matches bare `403`/`404` → PyPI 404 misreported as git auth; 300 s timeout branch untested. | `packages/datalab/src/datalab/new_project.py:22-24,82-90` | 8 subprocess | CONFIRMED | Partly | `test_pypi_404_is_not_classified_as_auth`, `test_uv_lock_timeout_is_reported` |
| 🔵 Info | Voice-arch unit tests read the developer's repo-root `.env` (absolute `env_file`, cached `load_settings()` at import). | `projects/voice-arch/src/voice_arch/settings.py:20`, `worker.py:36`, `tests/conftest.py:14-19` | 11 fresh-clone | CONFIRMED read, failure SUSPECTED | No | `test_unit_settings_ignore_repo_root_env` |

Unverified (needs Windows or load): `os.replace` on an open `run.json` on Windows; MLflow sqlite "database is locked" under concurrent writers; `tools/weavit-web.sh` partial build reuse.

### 7. CI Gate Surface

Full matrix: [`CI_REVIEW_2026-11-11.md`](CI_REVIEW_2026-11-11.md). Core verdict exit 0, but see the first row.

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 Warning | Inventory blind spot: `ci_gate_inventory.py` detects manifests at depth 0–1 only, so its exit 0 covers `app` alone; the five Python trees are undeclared (`.ci-gate-exemptions.json` has no `trees:`). With them declared (scratch copy) it still exits 0. | `.ci-gate-exemptions.json` | Gate inventory coverage | Declare the five trees under `trees:` so the verdict covers them. |
| 🟡 Warning | `templates/project` scaffold tests run only in CI (`-m 'not integration and not scaffold'` locally) — intentional (network for `uv lock`). | `packages/datalab/pyproject.toml:75`, `.github/workflows/ci.yml` | Local↔CI parity | Keep; documented in memory. Optionally a manual `pre-push` stage hook. |
| 🟡 Warning | App build: CI runs 5 `npm run build` fixture steps, `gates-app` hook runs none. | `.github/workflows/ci.yml`, `.pre-commit-config.yaml` | Local↔CI parity | Add one fixture build to the pre-push hook. |
| 🟡 Warning | No dependency audit for the root `gates-root` ad-hoc pins (pyright, pytest, pytest-cov, pyyaml). | `.pre-commit-config.yaml` | Dep audit | Low risk (dev tooling); pin via a root `uv.lock` or accept with an exemption. |
| 🟡 Warning | App has no JS SAST (`eslint-plugin-security` absent; no catalog template either). | `app/eslint.config.js` | SAST | Add `eslint-plugin-security` or record an exemption (static read-only site). |
| 🔵 Info | Tool pins consistent (ruff 0.17.3, pyright 1.1.414, pytest-cov 7.1.0, pip-audit 2.10.1, gitleaks 8.30.1); every tree has its own `fail_under = 70`. Linter freshness: 0 stale, 2 customized (`check_declared_dependencies`, `check_enum_discipline` — review, don't overwrite), 2 project-local. | — | — | None. |
| 🔵 Info | `.nvmrc` is `22` but `engines` requires `>=22.22.0`. | `.nvmrc`, `app/package.json` | Toolchain parity | Pin `.nvmrc` to `22.22`. |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [ ] ARCHITECTURE.md: add `contracts/value_sets.json`, the missing `tools/pre_commit_checks/*` entries, `.ci-gate-exemptions.json`, function-length hook line, hydra-core/omegaconf Tech Stack bullet.
- [ ] Add `SCOPING: Final` (`ledger_model.py`) and a named const for `'validated'` (`app/src/lib/ledger.ts:158`).
- [ ] Justify or remove the ~30 bare suppressions; typed `make_settings(**kw)` test helper.
- [ ] Tests: drop `len(contract["tags"]) == 11`; rewrite `test_f2_outside_source_follows_main` to assert only the scaffolded line; replace `"#48"` literal with a named token; split `test_f_9_close_runs_kills_only_given_ids`; add the `close_runs` "cannot be read" test.
- [ ] `.nvmrc` → `22.22`; declare the five Python trees in `.ci-gate-exemptions.json` `trees:`.
- [ ] `/plan-archive` the shipped platform plans and update ADR links.

### Phase 1 — Structural Improvements (medium effort)
- [ ] Bound MLflow retries in `project_spend`/`stale_runs`/`close_runs` (+ preflight in `voice_arch.decide`) with tests.
- [ ] Lock or compare-and-swap in `ledger.write_atomic` (+ stale-write and concurrent-look tests); report "committed" correctly when `_fsync_dir` fails after replace.
- [ ] Voice-arch budget: count FINISHED `cost_unknown` runs at estimate (replace `test_budget.py:84`).
- [ ] `.gitattributes` with `-text` for hashed files (`split.json`, `data/raw/**`) + CRLF-aware V-2 message.
- [ ] `datalab-new` robustness: clean tmp dir on `BaseException`, PyPI-404 vs auth classification, timeout test; `wiring.apply` tmp cleanup + LF writes.
- [ ] import-linter `forbidden` contracts for project isolation (and scaffolder emission).
- [ ] Ledger tests: independent literal transition table; assert blamed field/milestone in invalid vectors.

### Phase 2 — Architectural Changes (higher effort)
- [ ] Property-based tests (Hypothesis) for split invariants, `normalize`, name validation, ledger sequences vs I-1..I-15.
- [ ] Scenario traceability: catalogue ids in tests + parity test against `tests/TESTING_SCENARIOS.md`.
- [ ] Card status: transition map + CI diff check, or an ADR recording the exemption.
- [ ] App: `config.ts` as the sole env reader with validation; single `isDev`.

### Phase 3 — Ongoing Discipline
- [ ] Widen `check_file_size` / `check-function-length` to `tools/` (and an explicit decision on tests/app); split `check_enum_discipline.py` and `_layout.py::run_layer_check` first.
- [ ] ruff: add `ANN`, `N`, `T20`, `PGH003/004`; pyright `strict = ["tools"]`.
- [ ] Pre-push: one app fixture build; JS SAST or a recorded exemption; root dev-pin audit decision.

## Implementation-Notes Promotion (tier-3 flywheel)

| Deviation (from IMPLEMENTATION_NOTES.md) | Recurs? | Promote to | Action |
|---|---|---|---|
| Platform Phase 2: skill text hardcoded a milestone sequence and "repo root" wording beyond the plan's line list | 1× (one-off — repo-local skill moved to a portable plugin) | — | note; archive with this cycle via `/plan-archive` |

## Linter Candidates (3+ occurrences)

| Pattern | Files | Scaffold Command | Fix First |
|---------|-------|------------------|-----------|
| Suppression (`# type: ignore` / `# pyright: ignore` / `# noqa`) without a WHY | 15+ | ruff `PGH003`/`PGH004` in `ruff.toml`, or `/scaffold-linter suppression-justified` (generic grep check) | Phase 0 |
| File > 200 / function > 30 lines outside `src/` | 3 (`check_enum_discipline.py`, `_layout.py`, mini-rag test helpers) | widen existing `check_file_size` / `check_function_length` `files:` regex | Phase 3 |

Below threshold, worth watching: `MlflowClient(...)` built without `_bound_http_retries()` (3 sites, 1 file); `write_text` without `newline=` (2 files).

## Harness Gaps (a mechanical gate should have caught this)

| Finding | Gap type | Action |
|---------|----------|--------|
| `check_enum_discipline.py` (202 lines) and `_layout.py::run_layer_check` (31 lines) passed the gate | existing-check miss — `check_file_size` / `check-function-length` `files:` regex is `*/src/` only | widen the regex to `tools/`; add a fixture file under `tools/` proving it is checked |
| Cross-project / datalab→project imports unguarded | unguarded surface — import-linter contracts cover purity only | add `forbidden` contracts per tree |
| ~30 unjustified suppressions | unguarded surface — no rule checks suppression format | ruff `PGH003/004` or a suppression-format hook |
| CI inventory exit 0 while blind to 5 of 6 trees | existing-check miss in the harness tool (`ci_gate_inventory.py` depth 0–1 detection) | declare `trees:` here; harness issue for depth-2 detection in `_trees.py` |
| App JS SAST absent and no catalog template | unguarded surface (harness catalog gap) | harness issue: ship an `eslint-plugin-security` recipe |

**Workflow:** run `/plan-fix`, fix violations per phase, then close each harness gap (scaffold/repair the check + fixture) so the same class can't recur.
