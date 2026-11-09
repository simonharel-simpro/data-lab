# Fix Plan — Phase 1: Run integrity (empty index, #12 build race, voice-arch budget)

**Status:** ✅ Complete — branch fix-phase-1-run-integrity, 2026-11-08
**Severity:** 🔴
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules (routers/services/repositories).
**Depends on:** none
**Fix units:** 4
**Files affected:** 9
**Closes:** #12 (put `Closes #12` in the PR body)

Gates per tree (run in the tree's directory): `uv run --locked lint-imports && uv run --locked pyright && uv run --locked pytest -q --cov`. Every test added here is committed **red first** (a separate `test: ... (red)` commit that fails on the current code), then the fix.

## Within-phase Dependencies

- 1.1 → 1.3: both edit `ensure_collection` in `projects/mini-rag/src/mini_rag/index.py`. 1.3 wraps the reuse check that 1.1 rewrites, and the lock covers the probe too.
- 1.2 is independent (`run.py`).
- 1.4 is independent (voice-arch).
- Do **not** add a parameter to `ensure_collection` (it already has 6, and Phase 4.6 regroups it). The lock directory is a module constant that tests monkeypatch.

## ⛔ Do Not Restore

1.1 and 1.2 make two silent paths fail loudly: an index that holds objects but answers no vector search, and a run that scored on zero passages. The resulting `IndexBuildError` / `EmptyRetrieval` is the INTENDED outcome. DO NOT silence it with a fallback (for example "use BM25 when vector search is empty"), a `try/except: pass`, or a default passage list. The only acceptable fix is the rebuild, or a FAILED run.

## Fix Units

### Fix Unit 1.1: Reuse a collection only if a vector search answers (🔴 REVIEW §6 row 1)
- **Files:** `projects/mini-rag/src/mini_rag/index.py`, `projects/mini-rag/tests/test_index.py`
- **Violation pattern (Grep):** `exists\(name\) and _count\(client, name\) == len\(chunks\)`
- **Expected after fix:** 0 matches
- **Reference example:** `_count` (index.py:50) is the one-line helper style to copy. The 2026-11-07 incident (commit `95d70c1`): objects intact, HNSW commit log lost, every `near_text` empty.
- **HOW TO FIX:**
  1. **Red first.** In `test_index.py`, extend `_FakeCollections` with a `near_text_hits: list[dict[str, str]]` that the fake `query.near_text` returns (the fake already records `queries`/`hits`; reuse them). Add:
     - `test_reuse_with_matching_count_but_empty_vector_search_rebuilds`: `exists=True`, `counts=[3, 3]`, near_text returns no objects on the first probe and one hit after the rebuild. Assert exactly one `("delete", name)` + one `("create", name)` in `fake.calls`, and the returned name.
     - `test_rebuilt_collection_whose_vector_search_stays_empty_raises`: the probe is empty every time, so `IndexBuildError` matches `"vector search"`.
     - Keep `test_f_13_complete_collection_is_reused` green: give it a non-empty probe.
  2. In `index.py`, add `_searchable(client, name, probe: str) -> bool`: `collection.query.near_text(query=probe, limit=1)` and return `bool(res.objects)`. The probe text is `chunks[0].text`. It always exists, because `ensure_collection` is never called with zero chunks: add `if not chunks: raise IndexBuildError("no chunks to index")` at the top.
  3. Replace the reuse condition with `_complete(client, name, chunks) -> bool` = `exists and _count == len(chunks) and _searchable(...)`. Use the same `_complete` after each build in the `for attempt in (1, 2)` loop, so a rebuild whose vector index stays empty also ends in `IndexBuildError(f"collection {name} ... vector search returns nothing ...")`.
  4. Docstring of `ensure_collection`: "complete = right count AND a vector probe answers (the HNSW-loss incident)". Keep `index.py` ≤ 200 lines (today 101).

### Fix Unit 1.2: A question with zero retrieved passages fails the run (🔴 REVIEW §6 row 1, second half)
- **Files:** `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/tests/test_run.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `test_f_13_generation_error_marks_run_failed_without_metrics` (test_run.py:98). An error raised inside `_answer_all` already ends the run FAILED with no metrics, and the JSONL sink keeps the earlier answers.
- **HOW TO FIX:**
  1. **Red first.** `test_search_returning_no_passages_fails_the_run`: `search` returns `[]` for the 2nd question. Assert `pytest.raises(EmptyRetrieval, match=<question id>)`, run status `FAILED`, `"score" not in metrics`, and the sink holds exactly the 1st answer.
  2. In `run.py`, define `class EmptyRetrieval(RuntimeError)`. In `_answer_all`, right after `passages = find(...)`: `if not passages: raise EmptyRetrieval(f"question {q.id}: {retrieval} search returned no passages (empty index?)")`. Raise before calling `answer`, so no LLM money is spent.
  3. `main()`: the exception propagates like `GenerationError` (non-zero exit with a traceback-free message if `main` already maps errors; read `main()` and follow its existing pattern).
  4. `run.py` stays ≤ 200 lines (today 164).

### Fix Unit 1.3: Serialize index builds across concurrent runs (#12; REVIEW §4 row 2, §6 row 3)
- **Files:** `projects/mini-rag/src/mini_rag/index.py`, `projects/mini-rag/tests/test_index.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** target shape (mechanism **D-2**; P-1 answered by the user on 2026-11-08: flock):
  ```python
  LOCK_DIR: Final = Path(tempfile.gettempdir()) / "datalab-index-locks"

  @contextmanager
  def _build_lock(name: str) -> Iterator[None]:
      """One builder per collection name on this host; Weaviate is local (127.0.0.1), so the host is the scope."""
      LOCK_DIR.mkdir(parents=True, exist_ok=True)
      with (LOCK_DIR / f"{name}.lock").open("w") as handle:
          fcntl.flock(handle, fcntl.LOCK_EX)
          yield
  ```
- **HOW TO FIX:**
  1. **Red first.** `test_12_concurrent_ensure_collection_never_deletes_a_build_in_progress`. Use a thread-safe fake whose `batch.__exit__` waits on a `threading.Event` while caller A is inside it, then start caller B in a second thread. Assert: no `("delete", name)` happens between A's `create` and A's batch exit; both callers return the name; the final count equals `len(chunks)`; `create` is called once. `monkeypatch.setattr(index, "LOCK_DIR", tmp_path)`. Bound every wait with `timeout=5` so a regression fails, never hangs. On the current code the test must fail: B sees a partial count and deletes A's collection.
  2. Wrap the whole body of `ensure_collection` (reuse check, builds, raise) in `with _build_lock(name):`. Because the reuse check runs under the lock, B waits, then sees A's complete collection and reuses it (double-checked).
  3. Do not catch exceptions from the probe: with `t2v-transformers` down, `near_text` raises, and that error propagates (a catch-and-rebuild would waste a build; S-15b). Imports: `fcntl`, `tempfile`, `contextlib.contextmanager`, `Iterator`. data-lab runs on Linux/WSL (ADR 3). Add a comment that `fcntl` is POSIX-only.
  4. Docs: one line in `ARCHITECTURE.md` under the mini-rag data flow ("index builds are serialized per collection by a host-local file lock, #12"). One ADR in `decisions.md` ("Serialize Weaviate index builds with a host-local flock", with the P-1 alternatives; the lock files in the OS temp dir are never removed, which is fine for a local lab, S-15c).

### Fix Unit 1.4: voice-arch budget counts every dollar spent (🔴 REVIEW §6 row 2)
- **Files:** `projects/voice-arch/src/voice_arch/budget.py`, `projects/voice-arch/src/voice_arch/runner.py`, `projects/voice-arch/src/voice_arch/bench.py`, `projects/voice-arch/tests/test_budget.py`, `projects/voice-arch/tests/test_runner.py`
- **Violation pattern (Grep):** `_COUNTED_STATUSES`
- **Expected after fix:** 0 matches
- **Reference example:** `datalab.tracking_queries.project_spend` (packages/datalab/src/datalab/tracking_queries.py:57): "Sum of `cost_usd` over every run of the project, whatever its status (RUNNING counts: F-7)". It covers `voice-arch` and every `voice-arch/*` experiment and filters on `tags.project`. `Trial.add_cost` (tracking.py:47) is the cumulative-log rule.
- **HOW TO FIX:**
  1. **Red first** (sqlite MLflow store, as the existing budget tests do):
     - `test_running_run_with_cost_counts_toward_budget`: a RUNNING run with `cost_usd=3` → `spent_so_far(...) == 3`.
     - `test_sweep_logs_cumulative_cost_after_each_call`: a fake tracker whose `spent_now()` returns 0.5, then 1.25. After two calls, the run's `cost_usd` metric history is `[0.5, 1.25]` (steps 0, 1), before the summary is logged.
     - `test_unreadable_key_tags_cost_unknown`: `spent_now()` returns `None`, so the run has tag `cost_unknown=true`.
     - **Rewrite the existing `test_budget.py` tests** (S-6). They create runs with `client.create_run(...)` and no `project` tag, but `project_spend` filters on `tags.project = 'voice-arch'` (tracking_queries.py:46). Tag each run `project=voice-arch` and pass `make_settings(sqlite_uri)`, as `packages/datalab/tests/test_tracking.py:152` does.
  2. **D-1.** `budget.spent_so_far(settings: Settings) -> float` becomes `project_spend("voice-arch", settings)`. Delete `_COUNTED_STATUSES`, `_SUBS` and the hand-written pagination. Update both callers: `runner.py:174` and `bench.py:60`. They pass `dl` / `env.dl`, which they already hold. `runner.main` **keeps** its `MlflowClient`, because `partial(last_full_sweep_cost, client)` uses it. Only `bench._logged_run`'s client, built just for this call, goes away. Keep `check_budget` / `BudgetExceeded` unchanged.
  3. **Per-call cumulative cost.** `_Sweep._check_spend` already reads `now = tracker.spent_now()` after each call. Log it every time: `mlflow.log_metric("cost_usd", now, step=index)`, even for the last call (the budget check itself stays skipped after the last call). Pass `index` in from `calls`. `on_exit` logs the final value with `step=len(sweep.rows)`, so it never collides with the step-0 point from the first call (S-15a). Then `cost_usd`'s latest value is the cumulative spend, and a SIGKILL loses at most one call's cost.
  4. **`cost_unknown`.** When `now is None`, call `mlflow.set_tag("cost_unknown", "true")` once per run, next to the existing warning.
  5. **P-2 (user, 2026-11-08: count the estimate).** Do not import from `runner`/`bench` into `budget` (`runner` and `bench` import `budget`, so that would be circular). Move both estimates into `budget.py` as `ESTIMATES_USD: Final = {"conversations": 15.0, "bench": 2.0}` (today `runner.FALLBACK_ESTIMATE_USD` and `bench.ESTIMATE_USD`). `runner.py` and `bench.py` then import `ESTIMATES_USD["conversations"]` / `["bench"]` from `budget` and delete their own constants (grep the tests for the old names and update them). In `spent_so_far`, a `voice-arch/<sub>` run that is not FINISHED and has no `cost_usd` counts at `ESTIMATES_USD[sub]`, with `logger.warning("run %s has no cost_usd: counted at the %.2f $ estimate", ...)`. `project_spend` returns only a sum, so do this as one small query in `budget.py` that lists the cost-less, non-FINISHED runs per sub-experiment (`search_runs` with `filter_string="tags.project = 'voice-arch'"`). Test: `test_crashed_run_without_cost_counts_at_the_estimate`.
  6. **P-3 (user, 2026-11-08: keep fail-open).** Change nothing in the F-12 fail-open path. The `cost_unknown` tag from step 4 is the only addition.
  7. `runner.py` (184 lines) must stay ≤ 200. If step 3 pushes it over, move `_Sweep` into `voice_arch/sweep.py` (pure move, imports updated) in the same unit, and list it in the PR.
  8. Docs: ARCHITECTURE.md "Voice sweeps": the budget is `project_spend` (all statuses), cost is logged after every call, plus the P-2 rule.

## Verification

- `uv run --locked pytest -q` green in `projects/mini-rag` and `projects/voice-arch`. Every red-first test fails on `8f3add8` and passes after its fix.
- `grep -rn "_COUNTED_STATUSES" projects/voice-arch/src` → 0; `grep -n "exists(name) and _count" projects/mini-rag/src/mini_rag/index.py` → 0.
- `/check`, then a PR whose body says `Closes #12`.

<!-- plan-validate: READY 2026-11-08 sha256:7bc2170ec9ab -->
