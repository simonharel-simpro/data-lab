# Fix Plan — Phase 5: pyright strict on `src/` (#14)

**Severity:** 🟡
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules.
**Depends on:** Phases 1–4 (they change signatures and move code; strict types the final shape)
**Fix units:** 8
**Files affected:** 47 (each unit ≤ 8; 5.8 names the template `src/` directory)
**Closes:** #14 (put `Closes #14` in the PR body)

**Scope (#14 + the user's brief):** strict on `src/` only, in `packages/datalab`, `projects/mini-rag`, `projects/voice-arch` **and `templates/project`** (P-7); `tests/` stay `basic`. **P-6:** full strict in voice-arch, with casts at the SDK boundaries (both answered by the user on 2026-11-08).

**Mechanism:** pyright's `strict` path list, in the existing `[tool.pyright]` table of each tree. `typeCheckingMode = "basic"` stays the default for everything else (the tests):
```toml
[tool.pyright]
include = ["src", "tests"]
typeCheckingMode = "basic"
strict = ["src"]
pythonVersion = "3.12"
venvPath = "."
venv = ".venv"
```

**Baseline (2026-11-08, `8f3add8`, strict over `src/`):** datalab 38 errors / 10 files; mini-rag 20 / 6; voice-arch 142 / 28. Phases 1–4 move code, so re-measure after 5.1 with `uv run --locked pyright` in each tree, and fix by the file lists below. A file that is not listed but has errors goes to the batch of its tree with the most room (≤ 8 files per unit).

**Allowed fixes:** real annotations; `cast(...)` at an untyped third-party boundary (livekit, mlflow, weaviate, hydra, omegaconf) with a one-line comment naming the SDK call; a typed local wrapper when the same untyped call recurs; `# pyright: ignore[<rule>]  # <why>` only where no annotation can express the type. **Not allowed:** lowering a rule in config, `Any` without a reason, or a bare ignore.

## Within-phase Dependencies

5.1 first (config + `py.typed`: it clears the 17 `reportMissingTypeStubs` on `datalab.*` in the two projects). Then 5.2–5.7 in any order. The phase is green only when all of them land, so commits in between may be red on pyright: push once, at the end.

## Fix Units

### Fix Unit 5.1: Turn strict on for `src/`, mark `datalab` typed, explicit template mode
- **Files:** `packages/datalab/pyproject.toml`, `projects/mini-rag/pyproject.toml`, `projects/voice-arch/pyproject.toml`, `templates/project/pyproject.toml`
- **New files:** `packages/datalab/src/datalab/py.typed`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** the TOML block above.
- **HOW TO FIX:**
  1. Add `strict = ["src"]` to each of the four `[tool.pyright]` tables. Add `typeCheckingMode = "basic"` and `pythonVersion = "3.12"` where they are missing (voice-arch, template), so every tree states its mode explicitly.
  2. Create the empty `packages/datalab/src/datalab/py.typed`. Check that the build backend ships it (`[tool.hatch]` / setuptools `package-data` in `packages/datalab/pyproject.toml`); the projects use an editable install, so it is seen either way.
  3. The template is strict too (P-7). 5.8 owns its errors.
  4. voice-arch is full strict (P-6): no rule is lowered in config.
  5. Run `uv run --locked pyright` in each tree and save the error list. It is the work list for 5.2–5.7.

### Fix Unit 5.2: datalab, part 1 (11 + 7 + 6 + 5 baseline errors)
- **Files:** `packages/datalab/src/datalab/wiring_parity.py`, `packages/datalab/src/datalab/project.py`, `packages/datalab/src/datalab/tracking_queries.py`, `packages/datalab/src/datalab/tracking.py`, `packages/datalab/src/datalab/settings.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `@contextmanager` functions: annotate `-> Generator[T, None, None]` (`collections.abc`), not `Iterator[T]`. That clears the 3 `reportDeprecated` (settings.py:31, tracking.py:94, tracking.py:152).
- **HOW TO FIX:** fix every strict error in these files; `reportUnknown*` come from `yaml.safe_load` / mlflow returns, so `cast` the parsed value to its validated shape right after validation. `uv run --locked pyright` in `packages/datalab` lists 0 errors for these files.

### Fix Unit 5.3: datalab, part 2, plus mini-rag
- **Files:** `packages/datalab/src/datalab/wiring.py`, `packages/datalab/src/datalab/new_project.py`, `packages/datalab/src/datalab/ledger.py`, `packages/datalab/src/datalab/ledger_ops.py`, `packages/datalab/src/datalab/ledger_model.py`, `packages/datalab/src/datalab/split.py`, `projects/mini-rag/src/mini_rag/questions.py`, `projects/mini-rag/src/mini_rag/corpus.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `reportPrivateUsage` on `_revalidate` (ledger.py:30): rename `ledger_ops._revalidate` → `revalidate` (it is part of the ops' contract with the facade), and update both modules.
- **HOW TO FIX:** fix every strict error in these files. After this unit, `packages/datalab` has 0 pyright errors. `reportUnnecessaryIsInstance`: delete the redundant check only if the type really guarantees it at runtime; if the check guards untrusted JSON, type the input `object` instead.

### Fix Unit 5.4: mini-rag rest
- **Files:** `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/src/mini_rag/scoring.py`, `projects/mini-rag/src/mini_rag/generate.py`, `projects/mini-rag/src/mini_rag/index.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** weaviate `o.properties[...]` is `Unknown`, so `str(...)` it as `search` already does, and annotate the comprehension target.
- **HOW TO FIX:** fix every strict error in these files. After this unit, `projects/mini-rag` has 0 pyright errors.

### Fix Unit 5.5: voice-arch batch 1 (bench + audio + LLM adapters)
- **Files:** `projects/voice-arch/src/voice_arch/bench.py`, `projects/voice-arch/src/voice_arch/audio.py`, `projects/voice-arch/src/voice_arch/llm_guard.py`, `projects/voice-arch/src/voice_arch/naturalness.py`, `projects/voice-arch/src/voice_arch/bench_runs.py`, `projects/voice-arch/src/voice_arch/llm_dump.py`, `projects/voice-arch/src/voice_arch/rate.py`, `projects/voice-arch/src/voice_arch/bench_record.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `llm_dump.py`'s existing `fmt: str = stream._provider_fmt  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]` is the accepted form for a private livekit attribute: an annotated target plus a bracketed rule.
- **HOW TO FIX:** the bulk is `make_stt` / `make_tts` / `make_llm` returns and livekit plugin constructors with partially unknown signatures. Annotate their return types with the livekit base classes (`stt.STT`, `tts.TTS`, `llm.LLM`), so callers stop inheriting `Unknown`.

### Fix Unit 5.6: voice-arch batch 2 (agents + worker)
- **Files:** `projects/voice-arch/src/voice_arch/agents/arch_a.py`, `projects/voice-arch/src/voice_arch/agents/arch_b.py`, `projects/voice-arch/src/voice_arch/agents/tools.py`, `projects/voice-arch/src/voice_arch/agents/state.py`, `projects/voice-arch/src/voice_arch/worker_logic.py`, `projects/voice-arch/src/voice_arch/worker.py`, `projects/voice-arch/src/voice_arch/smoke_agent.py`, `projects/voice-arch/src/voice_arch/caller.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** for `session.on("event")` decorators (`reportUntypedFunctionDecorator`, `reportUnknownMemberType` on `on`): type the handler explicitly and register it with `session.on("x", handler)` instead of the decorator form.
- **HOW TO FIX:** fix every strict error in these files.

### Fix Unit 5.7: voice-arch batch 3 (calls, runner, budget, schemas, LiveKit imports)
- **Files:** `projects/voice-arch/src/voice_arch/live_caller.py`, `projects/voice-arch/src/voice_arch/runner.py`, `projects/voice-arch/src/voice_arch/budget.py`, `projects/voice-arch/src/voice_arch/tool_schemas.py`, `projects/voice-arch/src/voice_arch/booking/normalize.py`, `projects/voice-arch/src/voice_arch/dispatch.py`, `projects/voice-arch/src/voice_arch/livekit_env.py`, `projects/voice-arch/src/voice_arch/token.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `reportPrivateImportUsage`: import `CreateAgentDispatchRequest` / `RoomAgentDispatch` from `livekit.protocol.agent_dispatch`, and `DeleteRoomRequest` / `RoomConfiguration` from `livekit.protocol.room` (pyright's own suggestion).
- **HOW TO FIX:** fix every strict error in these files, then in any remaining voice-arch file (`call.py`, `decide.py`, `settings.py`, `sweep_query.py` had 1 each at baseline; if that pushes the unit past 8 files, put them in their own commit inside this unit and say so in the PR). After this unit, `projects/voice-arch` has 0 pyright errors.

### Fix Unit 5.8: Template `src/` strict errors (S-13; P-7)
- **Files:** `templates/project/src/__DATALAB_PACKAGE__`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `packages/datalab/tests/test_scaffold.py:42-43` runs the generated project's `uv run --locked pyright`.
- **HOW TO FIX:**
  1. Measure first. Nothing was measured at plan time, because the template has no venv. Run `uv run --locked pytest -m scaffold -q` in `packages/datalab` after 5.1. If it is green, this unit is done.
  2. If not, fix the reported errors in the template's `src/` (8 modules: `train.py`, `eval.py`, `prepare.py`, `split.py`, `grid.py`, `candidates.py`, `scoring.py`, `paths.py`) with the same allowed fixes. `train.py` (≈196) and `eval.py` (≈174) must stay ≤ 200 lines.
  3. If the fixes cannot fit without a split, stop and report. Do not lower the template's mode on your own.

## Verification

- `uv run --locked pyright` → `0 errors` in `packages/datalab`, `projects/mini-rag`, `projects/voice-arch`; `uv run --locked pytest -m scaffold -q` in `packages/datalab` (the generated project runs pyright at the template's mode).
- `grep -rn "pyright: ignore\[" packages/datalab/src projects/*/src | grep -v "  # "` → 0: every new ignore carries a reason.
- `/check`, then a PR whose body says `Closes #14`.

<!-- plan-validate: READY 2026-11-08 sha256:7eac8830e8f5 -->
