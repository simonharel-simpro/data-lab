# Fix Plan — Phase 4: Signatures, settings & error-handling style

**Status:** ✅ Complete — branch fix-phase-4-signatures-errors, 2026-11-08
**Severity:** 🟡
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules (routers/services/repositories).
**Depends on:** Phase 1 (1.3 changes `ensure_collection`, 1.4 changes `runner.py`), Phase 2 (2.5/2.6 change `call.py`)
**Fix units:** 10
**Files affected:** 24 (each unit ≤ 8)

**P-5 = A (user, AskUserQuestion 2026-11-08; scope decision D-6, #39).** 4.4 and 4.5 group the two 10-argument functions. 4.6–4.8 keep the other seven signatures and give each `def` a `# noqa: PLR0913  # <reason>`. 4.10 step 1 enables `PLR0913` in the same commit as 4.6–4.8 (see Within-phase Dependencies).

Measure before and after: `uvx ruff check --select PLR0913,BLE001 --output-format concise .` from the repo root. Baseline 17 `PLR0913` (9 src, 8 tests) and 3 `BLE001`.

Behaviour is unchanged in every unit: no test changes its assertions, only its call shape.

## Within-phase Dependencies

- 4.2 → 4.3: both edit `projects/voice-arch/src/voice_arch/settings.py`.
- 4.2 → 4.4: both edit `runner.py`'s `main()`.
- 2.5/2.6 (Phase 2) → 4.8: both change `call.py`.
- 4.4 → 4.8: both edit `runner.py`.
- 4.4/4.5 → 4.9: function lengths are measured after the regrouping.
- **4.6 + 4.7 + 4.8 + 4.10 step 1 land in ONE commit.** While `PLR0913` is not enabled, ruff's `RUF100` (unused `noqa`, selected via `RUF`) and the pre-commit `ruff-check --fix` hook strip every `# noqa: PLR0913`. So enable the rule (4.10 step 1) in the same commit that adds the `noqa` comments, never after it. 4.10 step 2 (test-helper annotations) may land separately.

## Fix Units

### Fix Unit 4.1: A reason on every broad `except`, and ruff `BLE001` on (REVIEW §2 row 3)
- **Files:** `projects/voice-arch/src/voice_arch/call.py`, `projects/voice-arch/src/voice_arch/live_caller.py`, `projects/voice-arch/src/voice_arch/worker_logic.py`, `templates/project/src/__DATALAB_PACKAGE__/eval.py`, `templates/project/src/__DATALAB_PACKAGE__/train.py`, `ruff.toml`
- **Violation pattern (Grep):** `except Exception:\s*$`
- **Expected after fix:** 0 matches
- **Reference example:** `call.py:136` `except Exception:  # the room may never have been created (dispatch failed): nothing left to delete`.
- **HOW TO FIX:**
  1. `call.py:132` (`_cleanup`, closing the caller): `except Exception:  # best-effort cleanup: a failed close must not hide the call's row`. `live_caller.py:160` (`close`, `session.aclose`): `except Exception:  # best-effort: the room is disconnected next whatever happened`. Narrow either one to the LiveKit error types instead, if the SDK documents them (check `.venv`).
  2. ruff `BLE001` does **not** flag those two (it accepts handlers that call `logger.exception`). It flags `worker_logic.py:122`, template `eval.py:140` and `train.py:138`, which already carry a reason. Rewrite each as `except Exception as err:  # noqa: BLE001  # <the existing reason>` (the `S603` style in `tools/pre_commit_checks/hydra_gate.py`).
  3. `ruff.toml` `[lint] select`: add `"BLE"`. `uvx ruff check .` from the root must be clean.

### Fix Unit 4.2: One `load_settings()` for voice-arch (REVIEW §1 row 1, §2 🔵 bare ignores)
- **Files:** `projects/voice-arch/src/voice_arch/settings.py`, `projects/voice-arch/src/voice_arch/worker.py`, `projects/voice-arch/src/voice_arch/smoke_agent.py`, `projects/voice-arch/src/voice_arch/runner.py`, `projects/voice-arch/src/voice_arch/dispatch.py`, `projects/voice-arch/src/voice_arch/token.py`, `projects/voice-arch/src/voice_arch/bench.py`
- **Violation pattern (Grep):** `VoiceSettings\(\)`
- **Expected after fix:** 1 matches (the single construction inside `load_settings`)
- **Reference example:** target shape, in `settings.py`:
  ```python
  @cache
  def load_settings() -> VoiceSettings:
      """The one place VoiceSettings is built from the environment: pydantic-settings fills the required fields."""
      return VoiceSettings()  # pyright: ignore[reportCallIssue]  # fields come from env / .env, not arguments
  ```
- **HOW TO FIX:**
  1. Add `load_settings()` as above (`functools.cache`).
  2. `worker.py` and `smoke_agent.py`: LiveKit pickles `entry` by module reference, so keep the module-level `server = AgentServer(...)`, built from `settings = load_settings()`. Add a one-line comment saying why the module-level server is kept (IMPLEMENTATION_NOTES Phase 2).
  3. `runner.py:160`, `dispatch.py:42`, `token.py:30`, `bench.py:151`: call `load_settings()` and drop each bare `# pyright: ignore[reportCallIssue]`.
  4. `bench.py:62`: replace `on_exit = lambda cost: ...  # noqa: E731` with a nested `def on_exit(cost: float) -> None:`.
  5. Tests that build settings via env + `VoiceSettings()` keep working. A test that changes env between calls must `load_settings.cache_clear()`: add an autouse fixture in `projects/voice-arch/tests/conftest.py` only if a test needs it (run the suite to see).

### Fix Unit 4.3: The dump directory is a `VoiceSettings` field (REVIEW §1 row 2)
- **Files:** `projects/voice-arch/src/voice_arch/settings.py`, `projects/voice-arch/src/voice_arch/llm_dump.py`, `projects/voice-arch/src/voice_arch/llm_guard.py`, `projects/voice-arch/src/voice_arch/worker.py`, `projects/voice-arch/tests/test_llm_dump.py`, `projects/voice-arch/tests/test_llm_guard.py`
- **Violation pattern (Grep):** `os\.environ\.get\(DUMP_DIR_ENV\)`
- **Expected after fix:** 0 matches
- **Reference example:** the other optional fields in `VoiceSettings`, e.g. `openrouter_quantization: str | None = None`.
- **HOW TO FIX:**
  1. `VoiceSettings.dump_empty_dir: Path | None = None`. The env name stays `VOICE_ARCH_DUMP_EMPTY_DIR` through the existing `env_prefix`. Keep the "must stay outside the repository" comment there.
  2. `dump_empty_request(stream, request, attempt, directory: Path | None)`: return `None` when `directory is None`. Delete `DUMP_DIR_ENV` and the `os` import.
  3. `llm_guard.py:49` gets the directory from whoever installs the guard. Read `llm_guard.py` and thread `dump_dir` through its installer (the worker passes `load_settings().dump_empty_dir`). Keep `llm_guard.py` ≤ 200 lines.
  4. Tests: `test_llm_dump.py` passes `tmp_path / "dumps"` or `None` instead of `monkeypatch.setenv`. `test_llm_guard.py:152`'s lambda gains the new parameter. Add `test_dump_dir_read_from_settings`: `VOICE_ARCH_DUMP_EMPTY_DIR=/x` gives `load_settings().dump_empty_dir == Path("/x")`.

### Fix Unit 4.4: Group `run_sweep`'s 10 parameters (REVIEW §2 row 2, §5 row 2: 35 lines)
- **Files:** `projects/voice-arch/src/voice_arch/runner.py`, `projects/voice-arch/tests/test_runner.py`
- **Violation pattern (Grep):** `async def run_sweep\(  # the plan fixes this signature`
- **Expected after fix:** 0 matches
- **Reference example:** mini-rag `RunConfig` (projects/mini-rag/src/mini_rag/run.py:38): a frozen dataclass of what identifies the run.
- **HOW TO FIX:**
  1. `@dataclass(frozen=True) class SweepPlan: personas: Sequence[Persona]; arch: Arch; reps: int` (what the sweep runs), and `@dataclass(frozen=True) class SweepContext: project: Project; dl_settings: Settings; voice: VoiceSettings; spent: float; last_full_cost: Callable[[], float | None]; spend_tracker: TrackerFactory` (where and with what budget). New signature: `async def run_sweep(env: CallEnv, plan: SweepPlan, ctx: SweepContext) -> str`.
  2. Extract `_open_sweep(...)` (the budget gate + `_Sweep` construction + tags) so that `run_sweep` is ≤ 30 lines. Keep `on_exit` and the `with (...)` block in `run_sweep`.
  3. Update `main()` and `test_runner.py:51`. The "the plan fixes this signature" comment goes: say in the PR that Phase 4 (P-5) supersedes the voice-arch plan's fixed signature.

### Fix Unit 4.5: Group and shorten `build_result` (REVIEW §2 row 2, §5 row 2: 41 lines)
- **Files:** `projects/voice-arch/src/voice_arch/worker_logic.py`, `projects/voice-arch/src/voice_arch/worker.py`, `projects/voice-arch/tests/test_worker.py`
- **Violation pattern (Grep):** `def build_result\(  # the plan fixes this 7-argument signature`
- **Expected after fix:** 0 matches
- **Reference example:** `CallResult` itself (result.py) is the target the parameters already mirror.
- **HOW TO FIX:**
  1. `@dataclass(frozen=True) class CallIdentity: room: str; arch: Arch; run_id: str` and `@dataclass(frozen=True) class SessionOutcome: state: BookingState; close: CloseEvent | None; errors: int; summarize_chat_ctx: bool | None; max_tool_steps: int; fatal: LLMError | None = None`. New signature: `build_result(call: CallIdentity, outcome: SessionOutcome, report_fn: Callable[[], dict[str, object]]) -> CallResult`.
  2. Extract `_problems(report_fn, close, fatal) -> tuple[dict[str, object] | None, list[str]]` so that `build_result` is ≤ 30 lines.
  3. Update `worker.py:78` and the six calls in `test_worker.py` (a small `_identity()` helper in the test keeps them short). `error_result` keeps its own signature if it has ≤ 5 parameters.

### Fix Unit 4.6: mini-rag: justify the four wide signatures (REVIEW §2 row 2; D-6, #39)
- **Files:** `projects/mini-rag/src/mini_rag/generate.py`, `projects/mini-rag/src/mini_rag/index.py`, `projects/mini-rag/src/mini_rag/run.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `tools/pre_commit_checks/hydra_gate.py`'s `# noqa: S603  # fixed argv: …` (a code, then the reason).
- **HOW TO FIX:**
  1. Add `# noqa: PLR0913  # <reason> (#39)` on the `def` line of `LlmGenerator.__init__` (connection settings, 4 defaulted), `ensure_collection` (index identity, kw-only), `_answer_all` and `run()`. For `run()`, the reason is: "grouped by role on 2026-11-04, S-10". Keep 1.1's probe and 1.3's lock unchanged.
  2. `uvx ruff check --select PLR0913 projects/mini-rag/src` → clean.

### Fix Unit 4.7: datalab: justify `ledger_ops.decide` (REVIEW §2 row 2; D-6, #39)
- **Files:** `packages/datalab/src/datalab/ledger_ops.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** as 4.6.
- **HOW TO FIX:** `# noqa: PLR0913  # redo_from / winner are optional kw-only options the /experiment skill passes by name (#39)` on the `def decide(` line. The public API is unchanged.

### Fix Unit 4.8: voice-arch: justify `run_one_call` and `make_llm` (REVIEW §2 row 2; D-6, #39)
- **Files:** `projects/voice-arch/src/voice_arch/call.py`, `projects/voice-arch/src/voice_arch/audio.py`
- **Violation pattern (Grep):** `# the plan fixes this signature`
- **Expected after fix:** 0 matches
- **Reference example:** as 4.6.
- **HOW TO FIX:**
  1. `call.py`: replace `# the plan fixes this signature` on `run_one_call` with `# noqa: PLR0913  # call identity + two timeouts, kw-only (#39)`. (4.4 already removed the `runner.py` comment.)
  2. `audio.py`: `# noqa: PLR0913  # all options but settings are defaulted (#39)` on `def make_llm(`.

### Fix Unit 4.9: The three first-party functions over 30 lines (REVIEW §5 row 2; P-11 answered on 2026-11-08)
- **Files:** `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/src/mini_rag/generate.py`, `packages/datalab/src/datalab/tracking.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** 4.4 step 2 (extract a cohesive private helper; no behaviour change).
- **HOW TO FIX:**
  1. Re-measure after 4.4–4.5: `python3 - <<'EOF'` + `ast` (FunctionDef `end_lineno - lineno + 1`) over the four files. Bring each of `run.run` (32), `LlmGenerator.__init__` (31) and `tracking.tracked_trial` (31, the 2.4 version) to ≤ 30 lines. Leave the vendored `_layout.run_layer_check` (31) untouched (D-9, #41).
  2. `run.run`: extract `_params(config, pilot, selected) -> dict[str, object]` (the `params |=` chain). `tracked_trial`: extract the tag validation (`if "project" in extra ...`) into `_trial_tags(tags, candidate, run_name)`. `__init__`: extract the client construction.
  3. The existing tests pass unchanged.
  4. Do not edit `tools/pre_commit_checks/_layout.py`: it is a vendored recipe, and its split is tracked in #41.

### Fix Unit 4.10: Enable `PLR0913`; annotate the three test helpers (REVIEW Linter Candidates; §2 🔵 helpers)
- **Files:** `ruff.toml`, `projects/voice-arch/tests/test_bench.py`, `projects/voice-arch/tests/test_call.py`, `projects/voice-arch/tests/test_corpus.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `ruff.toml` `[lint.per-file-ignores]` `"**/tests/**"`.
- **HOW TO FIX:**
  1. `ruff.toml`: add `"PLR0913"` to `select`, `[lint.pylint] max-args = 5`, and add `"PLR0913"` to `"**/tests/**"` in `per-file-ignores` (8 test helpers and fakes legitimately mirror wide signatures). `uvx ruff check .` must be clean.
  2. Return annotations: `test_bench.py:54` `def _corpus(tmp_path: Path) -> Corpus:`, `test_call.py:14` `async def _call(...) -> CallRow:`, `test_corpus.py:16` `async def _build(...) -> Corpus:` (check each return type).

## Verification

- `uvx ruff check --select PLR0913,BLE001 --output-format concise .` → clean (seven justified `noqa: PLR0913`, tests exempt).
- Every tree's gates green: `lint-imports && pyright && pytest -q --cov`, and `uv run --locked pytest -m scaffold -q` in `packages/datalab`.
- `/check`.

<!-- plan-validate: READY 2026-11-08 sha256:0a5912f66db9 -->
