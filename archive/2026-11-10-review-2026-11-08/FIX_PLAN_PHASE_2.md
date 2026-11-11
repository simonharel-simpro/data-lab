# Fix Plan — Phase 2: Resilience at the trust boundaries

**Status:** ✅ Complete — branch fix-phase-2-trust-boundaries, 2026-11-08
**Severity:** 🟡
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules. 2.7 is a bash script plus a pytest.
**Depends on:** none
**Fix units:** 7
**Files affected:** 17 (16 existing + 1 new)

Every unit adds a failing test first (a `test: ... (red)` commit), then the fix. Each refusal test's input must trip **exactly one** rule: prove it red with that rule removed (IMPLEMENTATION_NOTES: four refusal tests in the last cycle could not fail).

Template tree: the template is tested from its own suite, `cd templates/project && uv run --locked pytest -q` when a venv exists. CI tests it through `packages/datalab` `pytest -m scaffold`, which generates a project and runs its gates. Run both.

## Within-phase Dependencies

- 2.1 → 2.2 → 2.3: all three edit template `eval.py`.
- 2.5 → 2.6: both edit `projects/voice-arch/src/voice_arch/call.py`.
- 2.1, 2.4 and 2.7 are independent.

## ⛔ Do Not Restore

2.4 stops a `finally:` MLflow call from replacing the body's exception. 2.1, 2.2 and 2.3 turn a late or opaque crash into an early named refusal (exit 2). The named refusal is the INTENDED outcome. DO NOT catch it and continue training/evaluating, and DO NOT wrap the new checks in `try/except: pass`.

## Fix Units

### Fix Unit 2.1: Template train refuses a split / data hash that moved since the freeze (REVIEW §6 🟡 "Train never checks split.json")
- **Files:** `templates/project/src/__DATALAB_PACKAGE__/train.py`, `templates/project/src/__DATALAB_PACKAGE__/eval.py`, `templates/project/src/__DATALAB_PACKAGE__/prepare.py`, `packages/datalab/src/datalab/ledger.py`, `templates/project/tests/test_train.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `datalab.ledger_checks.check_split_hash(project_dir, ledger)` (ledger_checks.py:23-30) already raises `V-2: split.json changed after the freeze …`; template `eval.py:72-73` has the data-hash twin inline. `test_missing_split_exits_2` (test_train.py:192) is the exit-2-before-any-run test shape.
- **HOW TO FIX:**
  1. **Red first.** `test_train_refuses_split_changed_after_freeze_before_any_run`: a ledger with `split_sha256` frozen, then `split.json` edited, gives exit 2, stderr names `split.json`, and zero MLflow runs exist. Add the same test for `data_sha256` (data file edited).
  2. Reuse, do not rebuild (S-8). Export `check_split_hash` through the `datalab.ledger` facade if it is not exported yet. In `train.py` `_prepare`, keep the ledger read at step (4) in a variable `lg`, and, when `lg` is not None, call `ledger.check_split_hash(experiment_dir, lg)` (map `LedgerError` → `PrepareError`). Then do the same data-hash check that `eval.py:72-73` does when `lg.data_sha256` is set. Put both **before** `_candidates(cfg)`, so nothing is composed and no run is opened.
  3. Give that data-hash check a single home: `prepare.check_data_hash(expected: str | None, data_file: Path) -> None`. It does nothing when `expected is None`, and raises `PrepareError("data_file changed since modeling: its hash differs from run.json data_sha256")` (the existing eval wording) on a mismatch. Train calls it with `lg.data_sha256`, so it skips the check while that hash is None. Eval keeps its existing refusal when `lg.data_sha256` is None, as a separate check placed before the call (`if lg.data_sha256 is None: raise PrepareError(...)`; keep eval's current behaviour and wording), then calls `check_data_hash(lg.data_sha256, data_file)` in place of `eval.py:72-73`.
  4. `train.py` stays ≤ 200 lines (today 196): if it would not, take the two hash checks out of `_prepare` into one `_check_frozen(cfg, lg)` and shorten `_eval_part`, which recomputes the hashes for the tags. `PrepareError` is in `_REFUSALS`, so it exits 2.

### Fix Unit 2.2: Eval names a deleted / missing winner run (exit 2), not "tracking failed" (REVIEW §6 🟡)
- **Files:** `templates/project/src/__DATALAB_PACKAGE__/eval.py`, `templates/project/tests/test_eval.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `test_eval_refuses_winner_from_another_split` (test_eval.py:139).
- **HOW TO FIX:**
  1. **Red first.** `test_eval_with_deleted_winner_run_exits_2_naming_run`, in two cases. (a) The ledger's winner `run_id` does not exist: `client.get_run` raises `MlflowException` with `error_code == "RESOURCE_DOES_NOT_EXIST"`. (b) The run exists but `info.lifecycle_stage == "deleted"`. Both must exit 2, with stderr containing the run id and "does not exist" / "deleted".
  2. In `_check_winner`, wrap the first `client.get_run(gate.winner.run_id)`: catch `MlflowException` whose `error_code` is `RESOURCE_DOES_NOT_EXIST` (compare with `mlflow.protos.databricks_pb2.ErrorCode.Name(RESOURCE_DOES_NOT_EXIST)`) and re-raise it as `PrepareError(f"the winner run {id} does not exist in MLflow")`. Any other `MlflowException` stays an outage (exit 1). Then `if child.info.lifecycle_stage == "deleted": raise PrepareError(f"the winner run {id} is deleted")`. Do the same for the parent lookup.

### Fix Unit 2.3: tz-aware rows vs a naive `time_max` → `SplitError`, checked before the test look (REVIEW §6 🟡)
- **Files:** `templates/project/src/__DATALAB_PACKAGE__/split.py`, `templates/project/src/__DATALAB_PACKAGE__/eval.py`, `templates/project/tests/test_units.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `datalab.split._time_problem` (packages/datalab/src/datalab/split.py:115-124), "time_max values mix timezone-aware and naive dates", is the same rule between bounds. This unit adds it between rows and bounds.
- **HOW TO FIX:**
  1. **Red first.** In `test_units.py`: `test_load_split_tz_aware_rows_with_naive_bound_raises_split_error`, plus the reverse (naive rows, aware bound). Both raise `SplitError(match="timezone")`, never `TypeError`.
  2. In `split.py`, add `check_time_kinds(split: Split, rows: Sequence[Row]) -> None`. For a temporal split, compare `_when(row, col).tzinfo is None` for every row with the bounds' awareness, and raise `SplitError(f"{column!r} mixes timezone-aware and naive values with time_max")` on a mismatch. It reads only the time column, never the target. `_pick` calls it first.
  3. In `eval.py`, call `check_time_kinds(...)` inside `_gate` (or before `ledger.write_atomic` in `_score_test`), so a mixed-tz split exits 2 **before** a test look is recorded. Add a test in `test_units.py` or `test_eval.py`: after a mixed-tz eval, `run.json` `test_looks` is unchanged.

### Fix Unit 2.4: `tracked_run` / `tracked_trial` surface the body's error when the `finally` MLflow call fails (REVIEW §6 🟡)
- **Files:** `packages/datalab/src/datalab/tracking.py`, `packages/datalab/tests/test_tracking.py`, `packages/datalab/tests/test_tracking_trials.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `test_trial_slot_freed_when_cost_log_fails` (test_tracking_trials.py) patches the `finally` metric log; copy its patching style.
- **HOW TO FIX:**
  1. **Red first.** `test_tracked_run_surfaces_the_body_error_when_tagging_fails`: the body raises `KeyError("body")` and `mlflow.set_tags` (patched) raises `MlflowException` inside `_tag_outcome`. Assert that `KeyError` is raised and that `"tagging the outcome failed"` is in its `__notes__`. Add the same test for `tracked_trial` with `log_metric("cost_usd")` failing.
  2. In `tracked_run`, replace `finally: _tag_outcome(...)` with `except BaseException as err: _after_failure(err, lambda: _tag_outcome(run_id)); raise` / `else: _tag_outcome(run_id)`. `_after_failure` runs the callable; if that raises `Exception`, it does `err.add_note(f"tagging the outcome failed: {cleanup_err!r}")` and `logger.warning(...)`, then returns. The body error then propagates. On success, a tagging failure still raises, as today.
  3. Do the same in `tracked_trial` for the `finally: mlflow.log_metric("cost_usd", ...)`.
  4. `tracking.py` is at 183/200. If the change passes 195 lines, move `_Outcome`, `_OUTCOMES`, `_tag_outcome` and `_after_failure` into `datalab/tracking_outcome.py` (pure move). Add it to the import-linter "pure" list in `packages/datalab/pyproject.toml` **only** if it has no mlflow import, which `_tag_outcome` does have, so leave it out.

### Fix Unit 2.5: Bound every LiveKit step of a call (REVIEW §6 🟡 "Parts of a call have no deadline")
- **Files:** `projects/voice-arch/src/voice_arch/call.py`, `projects/voice-arch/tests/test_call.py`
- **Violation pattern (Grep):** `await (env\.(create_dispatch|connect_caller|delete_room)|handle\.close)\(`
- **Expected after fix:** 0 matches
- **Reference example:** `wait_agent` in `live_caller.py` uses `asyncio.wait_for(...)` and catches `TimeoutError`.
- **HOW TO FIX:**
  1. **Red first.** `test_run_one_call_bounds_a_dispatch_that_never_returns`: a fake `create_dispatch` awaits an `asyncio.Event` that is never set, with `monkeypatch.setattr(call, "STEP_TIMEOUT_S", 0.05)`. Assert `LiveKitUnresponsive(match="create_dispatch")` and that `_cleanup` still ran. Add the same for `connect_caller`. Add `test_cleanup_bounds_a_close_that_never_returns`: a hanging `handle.close`, then `run_one_call` returns its row within 1 s and a warning is logged.
  2. In `call.py`: `STEP_TIMEOUT_S: Final = 30.0` and `class LiveKitUnresponsive(RuntimeError)`. Add a helper `async def _bounded(step: str, aw: Awaitable[T]) -> T` that applies `asyncio.wait_for(aw, STEP_TIMEOUT_S)` and maps `TimeoutError` to `LiveKitUnresponsive(f"{step} did not answer within {STEP_TIMEOUT_S:.0f} s")`. Use it for `create_dispatch` and `connect_caller`.
  3. In `_cleanup`, wrap `handle.close()` and `env.delete_room(room)` in `asyncio.wait_for(..., STEP_TIMEOUT_S)`. A `TimeoutError` there is logged (`logger.warning(..., exc_info=True)`) and swallowed, like the existing failures: cleanup is best-effort.
  4. **P-4 (user, 2026-11-08: abort).** `LiveKitUnresponsive` propagates out of `run_one_call`, so the sweep's `tracked_run` marks the run FAILED and the rows so far stay in the JSONL.
  5. `call.py` stays ≤ 200 lines (today 161).

### Fix Unit 2.6: An interjection on a caller session that never started yields a CALLER_FAULT row (REVIEW §6 🟡)
- **Files:** `projects/voice-arch/src/voice_arch/live_caller.py`, `projects/voice-arch/src/voice_arch/call.py`, `projects/voice-arch/tests/test_live_caller.py`, `projects/voice-arch/tests/test_call.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `_run_session`'s `except Exception as err:` sets `self.caller_error` (live_caller.py:73-86).
- **HOW TO FIX:**
  1. **Red first.** `test_interject_on_unstarted_caller_yields_caller_fault_row` (test_call.py, through `call_fakes`): the caller's `caller_error` is set, `_started` is False and `interject` would raise `RuntimeError`, so `run_one_call` returns a row with `Outcome.CALLER_FAULT` and does not raise. In `test_live_caller.py`: `interject` on an unstarted `LiveCaller` does not call `session.say`, and `say` raising `RuntimeError` on a started caller sets `caller_error`.
  2. `LiveCaller.interject`: `if not self._started or self.caller_error is not None: return`. Wrap `self._session.say(...)` in `except RuntimeError as err:` → `self.caller_error = f"interjection failed: {type(err).__name__}"`. Narrow the exception to what `say` raises; check the livekit source in `.venv`.
  3. `call._classify`: check `handle.caller_error is not None` **first**, so a caller that never started is `CALLER_FAULT` even when no result arrives. Run the whole voice-arch suite: if an existing test pins `TIMEOUT` with `caller_error` set, stop and report it. Do not silently re-pin it.

### Fix Unit 2.7: `tools/weavit-web.sh` reads the key cleanly and fails clearly (REVIEW §6 🟡)
- **Files:** `tools/weavit-web.sh`
- **New files:** `tests/test_weavit_web.py`
- **Violation pattern (Grep):** `cut -d= -f2-|\[ ! -d node_modules \]`
- **Expected after fix:** 0 matches
- **Reference example:** `tests/test_compose.py` (root test, run by CI as `uvx pytest tests/`).
- **HOW TO FIX:**
  1. Move the key extraction into `read_env_key() { ... }`. It reads the first `^OPENROUTER_API_KEY=` line, takes `${line#*=}`, strips a trailing `\r`, then one pair of matching surrounding `"` or `'` quotes. Then: `if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return 0; fi`, placed after the function definitions and before any side effect, so tests can `source` the script.
  2. Guard the submodule: `[ -f "$root/tools/weavit-ui/package.json" ] || { echo "weavit-web: tools/weavit-ui is empty: run git submodule update --init tools/weavit-ui" >&2; exit 1; }`.
  3. Interrupted install: always run `pnpm_ install --frozen-lockfile` (it is idempotent and takes seconds when up to date), and drop the `[ ! -d node_modules ]` condition (S-12).
  4. `tests/test_weavit_web.py`, using `subprocess.run(["bash", "-c", 'source tools/weavit-web.sh; read_env_key "$1"', "_", str(env)])` with argv and no shell interpolation. Cases: `OPENROUTER_API_KEY="k"\r\n` → `k`; `'k'` → `k`; `k` → `k`; a missing key → empty. Plus a test that copies the script to `tmp_path/tools/weavit-web.sh` next to an empty `tmp_path/tools/weavit-ui/` (the script derives `root` from its own path) and runs it: exit 1, and stderr says `git submodule update --init`. If node < 22 is on PATH, the node check exits first, so put the submodule guard before the node check. Skip with `pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent (#8)")`.

## Verification

- `uv run --locked pytest -q` green in `packages/datalab` (incl. `-m scaffold`), `projects/voice-arch`; `uvx pytest tests/` green at the root.
- `grep -nE 'cut -d= -f2-|\[ ! -d node_modules \]' tools/weavit-web.sh` → 0; the 2.5 pattern → 0 in `call.py`.
- `/check`.

<!-- plan-validate: READY 2026-11-08 sha256:c2519430b20f -->
