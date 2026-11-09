# Review Validation Report — data-lab

**Date:** 2026-11-09
**Review date:** 2026-11-08
**Project type:** monorepo — python (datalab, mini-rag, voice-arch, project template, root tools), Astro/TS app
**Validated at:** `main` @ `910808c` (fix PR #42 merged) · **Healed:** 2026-11-09 on `fix/heal-review-2026-11-09` (uncommitted), 6/6 gaps

## Validation Summary

| Category | Findings Checked | ✅ Pass | ⚠️ Partial | ❌ Fail | ⏭️ Deferred | Completion* |
|----------|-----------------|---------|------------|---------|-------------|------------|
| Architecture & SoC | 4 | 4 | 0 | 0 | 0 | 100% |
| Typing & Style | 5 | 5 | 0 | 0 | 0 | 100% |
| State & Enums | 6 | 6 | 0 | 0 | 0 | 100% |
| Testing | 4 | 4 | 0 | 0 | 0 | 100% |
| Documentation & Debt | 5 | 5 | 0 | 0 | 0 | 100% |
| Resilience & Failure Modes | 11 | 10 | 0 | 0 | 1 | 100% |
| CI Gate Surface | 2 | 1 | 0 | 0 | 1 | 100% |
| **Migration Plan** | 26 | 25 | 0 | 0 | 1 | 100% |
| **TOTAL** | 63 | 60 | 0 | 0 | 3 | **100%** |

*Completion % = Pass / (Pass + Partial + Fail). Deferred items are excluded from the denominator.

## Overall Verdict

⚠️ **GAPS FOUND** — 0 findings partially or not addressed (100 % of the 60 non-deferred IDs pass after the 2026-11-09 heal). The verdict is capped only because two review-only tools (bandit, radon) are not installed in any tree, kept as is by user decision 2026-11-09. Nothing left for `/heal-review`.

Both 🔴 criticals (F6.1, F6.2) are resolved, with tests.

## Detailed Results

### 1. Architecture & Separation of Concerns
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F1.1 | ✅ PASS | Settings + server built at import time | all voice-arch src | 0 | One cached `load_settings()` (`settings.py:90-92`) with one justified ignore; worker/smoke_agent keep module-level `server` (LiveKit pickles `entry` by module), as REVIEW recommended |
| F1.2 | ✅ PASS | Env read outside the settings module | src of every tree | 0 | `dump_empty_dir` is a `VoiceSettings` field (`settings.py:61`), threaded via `audio.py:57` |
| F1.3 | ✅ PASS | ARCHITECTURE "Shared package" lists only some modules | ARCHITECTURE.md vs `packages/datalab/src/datalab` | 0 | Every module listed, pure ones marked (`ARCHITECTURE.md:106-125`) |
| F1.4 | ✅ PASS | voice-arch flat modules; layer text incomplete | every `voice_arch` module, pyproject contracts | 0 | Module→layer table (`ARCHITECTURE.md:248-262`); pure row = import-linter contract "pure modules stay MLflow-free"; `sweep_query` on the runs side |

### 2. Typing & Style
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F2.1 | ✅ PASS | pyright basic in every tree (#14) | 4 trees' pyproject; pyright -p run in 3 | 0 | `strict = ["src"]` per tree (tests basic); 0 errors in datalab, mini-rag, voice-arch; template covered by its scaffold test |
| F2.2 | ✅ PASS | >5 parameters in 9 src functions | AST scan of all src; ruff PLR0913 | 0 unjustified | REVIEW's recommendation done: `run_sweep`/`build_result` regrouped into dataclasses, `PLR0913` enabled (max 5). The other 7 keep `noqa: PLR0913` with a reason by user cut D-6 / P-5=A (#39) |
| F2.3 | ✅ PASS | `except Exception` without re-raise or WHY | every `except Exception` in src + tools | 0 | All carry a reason / `noqa: BLE001`; ruff `BLE` enabled and green |
| F2.4 | ✅ PASS | app/ has no formatter or linter (#13) | app/package.json, eslint config, hook, CI | 0 | eslint + prettier pinned, `gates-app` + CI steps, ADR 2026-11-09 |
| F2.5 | ✅ PASS | modules lack `from __future__ import annotations` | decisions.md, ARCHITECTURE.md | 0 | Resolved by decision — ADR "No `from __future__ import annotations` on py312+" (P-8, user 2026-11-08) |

### 3. State Management & Enums
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F3.1 | ✅ PASS | Ledger value sets defined twice, no pin test | contracts, Py + TS ledger | 0 | `contracts/value_sets.json`; Python `test_ledger_enums_match_contract` and TS deepEqual test both read it |
| F3.2 | ✅ PASS | No declarative milestone transition map | ledger_model/ops, tests, ARCHITECTURE | 0 | `TRANSITIONS` consulted by `_next` (produce/decide); exhaustive pair test + table↔ARCHITECTURE.md test |
| F3.3 | ✅ PASS | Raw status/decision/milestone literals in ledger ops | all Python src; enum-discipline hook in 3 trees | 0 | `ledger_ops.py` clean; milestone constants pinned to `milestones.json`. Note: `app/src/lib/ledger.ts:156` compares to `'validated'`, but `entry.status` is typed from `STATUSES`, so `tsc` catches a rename |
| F3.4 | ✅ PASS | Card FSM documented but unenforced | ARCHITECTURE.md, card.ts | 0 | Documented as a hand-edited label (plan D-5) |
| F3.5 | ✅ PASS | Repeated literals for fixed sets | project.py, tracking_queries, best.ts, decide, bench, template | 0 | `Goal` StrEnum + contract pin (Py + TS), `RunStatus`, `Outcome`, `Component` enums |
| F3.6 | ✅ PASS | Milestone id is a plain str | decisions.md, ledger_model | 0 | Resolved by decision — ADR "Milestone ids stay data-driven strings" (P-10, user); named ids are `Final` constants with a test |

### 4. Testing Quality
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F4.1 | ✅ PASS | 1 test skipped (`test_new_project.py:221`) | all Py + TS tests | 0 | Skip reason now "platform-conditional (#8)"; #8 body has the category |
| F4.2 | ✅ PASS | #12 ensure_collection race has no test | mini-rag tests | 0 | `test_index_concurrency.py`: two real threads, asserts one create, no delete mid-build |
| F4.3 | ✅ PASS | `datalab.split` rejection tests assert only the type | packages/datalab/tests | 0 | All `SplitError` raises in datalab tests use `match=`; parametrized rule test added. (Template `load_split` tests: see M0.4) |
| F4.4 | ✅ PASS | Count-only magic number on milestone sequences | test_ledger.py | 0 | Full id tuples asserted |

### 5. Documentation & Cognitive Debt
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F5.1 | ✅ PASS | ledger_ops.py at 199/200 | ledger*.py | 0 | 173 lines; access helpers in `ledger_access.py` |
| F5.2 | ✅ PASS | Functions over 30 lines | AST scan of all src + tools | 0 first-party | REVIEW asked to split `build_result` ("the others are marginal"): done, and every first-party function ≤ 30. Vendored `_layout.run_layer_check` (31) stays by user cut D-9 / P-11 (#41) |
| F5.3 | ✅ PASS | Floating dev dependencies | decisions.md, pyprojects | 0 | Resolved by decision — ADR "Dev dependency specs stay `>=`; uv.lock is the pin" (P-9, #40) |
| F5.4 | ✅ PASS | /experiment skill undocumented | ARCHITECTURE.md:87-89 | 0 | Listed with references + `.claude/hooks/` |
| F5.5 | ✅ PASS | stop_grace_period (#36) undocumented | ARCHITECTURE.md:99-101 | 0 | Infra layer bullet, incl. the hard-kill residual risk |

### 6. Resilience & Failure Modes
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F6.1 | ✅ PASS | 🔴 Empty vector index reused as complete | mini-rag index/run + tests | 0 | Count + `near_text` probe, rebuild once then `IndexBuildError`; `EmptyRetrieval` fails the run; tests for both |
| F6.2 | ✅ PASS | 🔴 voice-arch budget under-counts spend | budget, sweep, runner, bench, tracking_queries + tests | 0 | `spent_so_far` = project_spend (all statuses) + estimates for unmeasured runs; cumulative per-call `cost_usd`; `cost_unknown` tag; tests |
| F6.3 | ✅ PASS | #12 build with no lock | mini-rag index + concurrency test | 0 | `fcntl.flock` per collection around check/build/re-check; interleaving test |
| F6.4 | ✅ PASS | Train never checks frozen hashes | template prepare/train + tests | 0 | `frozen_score_on` before any run; refusal exit 2; tests assert zero experiments |
| F6.5 | ✅ PASS | Parts of a call have no deadline | call.py, livekit_env, live_caller + tests | 0 | dispatch/connect bounded (`LiveKitUnresponsive`), cleanup bounded; hang tests |
| F6.6 | ✅ PASS | Interjection on unstarted caller kills sweep | live_caller, call + tests | 0 | `interject` returns early; `say` errors → CALLER_FAULT; tests |
| F6.7 | ✅ PASS | Original error masked during MLflow outage; run can stay RUNNING | tracking.py, tracking_outcome + tests | 0 | Healed 2026-11-09: `tracking_outcome.ending_run` ends the run explicitly; a failing `end_run(FAILED)` goes through `after_failure` (body error kept, note added). mlflow pops the run off its active stack before the store call (fluent.py), so the next run is top-level; the store keeps it RUNNING until `stale_runs`/`close_runs`. 4 tests, each seen red |
| F6.8 | ✅ PASS | Missing/deleted winner run reported as tracking failure | template eval + tests | 0 | `PrepareError` naming the run, exit 2, no look recorded; parametrized test |
| F6.9 | ✅ PASS | tz-aware vs naive temporal split → raw TypeError | template split/eval/train + tests | 0 | `SplitError` before any test look; unit + eval tests |
| F6.10 | ✅ PASS | weavit-web.sh malformed key / opaque failure | tools/weavit-web.sh + tests | 0 | CR/quote stripping, submodule guard, always `pnpm install --frozen-lockfile`; tests |
| F6.11 | ⏭️ DEFERRED | Env-dependent skips (#8) | FIX_PLAN Deferred Items | — | Deferred in FIX_PLAN.md — #8 (excluded from completion %) |

### 7. CI Gate Surface
| ID | Status | Original Finding | Scope Checked | Files Still Affected | Details |
|----|--------|-----------------|---------------|---------------------|---------|
| F7.1 | ⏭️ DEFERRED | ci_gate_inventory sees 1 of 5 trees | FIX_PLAN Deferred Items | — | Deferred in FIX_PLAN.md — #37 (harness fix; hand audit kept) |
| F7.2 | ✅ PASS | tools/ + root tests/ have no type/test gate (#7) | hooks, CI, exemptions, pyrightconfig, tests | 0 | `gates-root` pre-push hook (pyright + pytest --cov=tools ≥ 70), run in CI; passes in the §9 pre-push row |

### 8. Simpro Cloud & AI Patterns
Not present in REVIEW.md.

### 9. Tooling Verification
`gate_runner.py python-fastapi --root packages/datalab --review` on the healed tree (branch `fix/heal-review-2026-11-09` off `910808c`, uncommitted; record: `REVIEW_GATE.json`). The pre-push row runs every tree's gate: `gates-root`, `gates-datalab`, `gates-mini-rag`, `gates-voice-arch`, `gates-app` (eslint, prettier, astro check, tests). A first run failed that row only because this checkout's `app/node_modules` predated the merge (no eslint); `npm ci` from the committed lockfile fixed it (`npm audit`: 0).

| Tool | Command | Exit | Status | Detail |
|------|---------|------|--------|--------|
| pre-commit pre-push | `pre-commit run --all-files --hook-stage pre-push` | 0 | ✅ PASS | app lint + format check + astro check + unit tests + coverage floor.......................Passed |
| pyright | `uv run pyright` | 0 | ✅ PASS | 0 errors, 0 warnings, 0 informations |
| ruff | `uv run ruff check .` | 0 | ✅ PASS | All checks passed! |
| lint-imports | `uv run lint-imports` | 0 | ✅ PASS | Contracts: 1 kept, 0 broken. |
| pytest | `uv run pytest` | 0 | ✅ PASS | ========== 233 passed, 3 deselected, 2 warnings in 154.60s (0:02:34) =========== |
| bandit | `uv run bandit -r src/ -c pyproject.toml` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |
| radon | `uv run radon cc src/ -a -nc` | 2 | ⛔ NOT INSTALLED | Caused by: No such file or directory (os error 2) |

gate exit 2: a tool is NOT INSTALLED — gate incomplete. bandit and radon are review-only extras that no tree declares (ruff's `S` rules are the SAST in the commit/CI gates).

### 10. Migration Plan Items
| ID | Status | Phase | Item | Details |
|----|--------|-------|------|---------|
| M0.1 | ✅ PASS | Phase 0 | WHY comments on `Any` / `except` / pragmas | Healed 2026-11-09: `llm_dump.py` `Any` has a WHY; every non-vendored pragma repo-wide now carries a reason (same line, or the line above when 120 chars would be exceeded) |
| M0.2 | ✅ PASS | Phase 0 | Pin floating dev deps `==` | Resolved by decision — ADR "Dev dependency specs stay `>=`" (P-9, #40) |
| M0.3 | ✅ PASS | Phase 0 | Annotate test helpers; bench lambda; diagnostic print | Done (`bench.py` `on_exit`, hydra_gate stderr, test_bench helpers annotated) |
| M0.4 | ✅ PASS | Phase 0 | `match=` on every `pytest.raises(SplitError)`; milestone id lists | Healed 2026-11-09: `match=` on the 3 template raises (exact messages from split.py); 0 bare `pytest.raises(SplitError)` repo-wide |
| M0.5 | ✅ PASS | Phase 0 | Docs: skill, grace period, card-status, module list | All in ARCHITECTURE.md |
| M0.6 | ✅ PASS | Phase 0 | "platform-conditional" category in #8 | Issue #8 body + skip reason |
| M0.7 | ✅ PASS | Phase 0 | hydra_gate timeout; weavit-web.sh hardening | Done, with tests |
| M1.1 | ✅ PASS | Phase 1 | Split ledger_ops.py; no raw literals | 173 lines + `ledger_access.py`; enums/constants |
| M1.2 | ✅ PASS | Phase 1 | Ledger enum contract + Py/TS equality tests | `contracts/value_sets.json` + both tests |
| M1.3 | ✅ PASS | Phase 1 | `load_settings()` factory; `dump_empty_dir` setting | Done |
| M1.4 | ✅ PASS | Phase 1 | Parametrized split rules + one Hypothesis property | Resolved by decision — D-3 approved by the user 2026-11-09 (FIX_PLAN.md D-3, ADR "Split leakage property: exhaustive enumeration instead of Hypothesis"); the enumeration property covers all 4^4 assignments |
| M1.5 | ✅ PASS | Phase 1 | voice-arch module→layer table; sweep_query purity | Done |
| M1.6 | ✅ PASS | Phase 1 | Dataclasses for run_sweep / build_result | `SweepPlan`/`SweepContext`, `CallIdentity`/`SessionOutcome` |
| M1.7 | ✅ PASS | Phase 1 | mini-rag vector probe + fail on zero passages | Done, tested |
| M1.8 | ✅ PASS | Phase 1 | Budget: cumulative cost, RUNNING runs, cost_unknown | Done, tested |
| M1.9 | ✅ PASS | Phase 1 | Template hash refusal; eval winner; tz SplitError | Done, tested |
| M1.10 | ✅ PASS | Phase 1 | tracking.py surfaces the body error when finally fails | `after_failure` (the `end_run` exit path is tracked under F6.7) |
| M2.1 | ✅ PASS | Phase 2 | Declarative TRANSITIONS + test | Done |
| M2.2 | ✅ PASS | Phase 2 | #12 serialized builds + interleaving test | flock + test + ADR |
| M2.3 | ✅ PASS | Phase 2 | #14 pyright strict on src/ per tree | Done in all 4 trees |
| M2.4 | ✅ PASS | Phase 2 | voice-arch call deadlines; CALLER_FAULT; error CallResult on worker setup failure | Healed 2026-11-09: `worker.entry` wraps `start_session` (session construction + `session.start`) and sends `error_result("worker setup failed: …")` then returns; cancellation propagates. `tests/test_worker_setup.py` (seen red) |
| M3.1 | ✅ PASS | Phase 3 | #13 eslint + prettier, gates-app + CI | Done |
| M3.2 | ✅ PASS | Phase 3 | ruff PLR0913 + BLE001; decide FA | Enabled; FA decided by ADR (P-8) |
| M3.3 | ✅ PASS | Phase 3 | Extend check_file_size.py to templates/*/src; consider a function-length check | Healed 2026-11-09: `ROOTS` + hook regex include `templates`, test added (seen red); new `check-function-length` pre-commit hook (functions ≤ 30, classes ≤ 150) over the same scope, wired locally and in CI (`verify_check_wired` exit 0) |
| M3.4 | ✅ PASS | Phase 3 | #7 tools/ type + test gate | `gates-root` hook + CI |
| M3.5 | ⏭️ DEFERRED | Phase 3 | Keep the hand audit until the inventory gap closes | Deferred in FIX_PLAN.md — #37 |

## Remaining Gaps (for /heal-review)

All six gaps from the 2026-11-09 validation were healed on 2026-11-09 (`/heal-review`): F6.7 (explicit `end_run`), M2.4 (worker setup error result), M3.3 (size check covers templates + function-length hook), M0.1 (WHY on every pragma), M0.4 (`match=`), M1.4 (D-3 approved). Also fixed while verifying: `packages/datalab/tests/test_scaffold.py:81` read stdout after Phase 8 moved the hydra-gate line to stderr, which had turned `main`'s CI red since PR #42.

No finding gap remains. The verdict stays capped only by the two review-only tools (bandit, radon) not installed in any tree — kept as is by user decision 2026-11-09.

## Deferred Items (not in scope for /heal-review)

| Item (inventory ID inline, e.g. "F2.3 — …") | Tracker | Reason for Deferral |
|------|---------|-------------------|
| F6.11 — environment-dependent skips (uv / docker / stack down) | #8 | CI has docker + uv; the skips only happen on a bare machine |
| F7.1 — ci_gate_inventory sees 1 of 5 trees | #37 | The fix belongs in the harness (`_trees.py`) |
| M3.5 — keep the hand audit of the Python trees | #37 | Until the inventory harness gap is closed |
