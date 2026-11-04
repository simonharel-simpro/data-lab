# Fix Plan — Phase 1: Run integrity & resilience (pilot)

**Severity:** 🔴 (1.1, 1.2 — the two halves of REVIEW §6's 🔴 row), 🟡 (1.3–1.5)
**Agent:** python-fastapi. This is generic Python: ignore the router/service/repository rules. Follow the package's own style (pydantic-settings, frozen dataclasses, F-/U- ids in docstrings, tests named `test_<id>_<behaviour>`).
**Depends on:** none
**Fix units:** 5
**Files affected:** 16

Context: `projects/mini-rag` is a RAG pilot. `run.py` answers 20 questions with a DGX LLM, scores them, and logs to MLflow through `datalab.tracking.tracked_run`. The tests use a real SQLite MLflow (`sqlite_uri` fixture) and a hand-built Weaviate fake (`tests/test_index.py`). Gates: `uv run pytest --cov` in `projects/mini-rag` (floor 70) and `uv run pytest --cov=datalab` in `packages/datalab`.

## Within-phase Dependencies

`run.py`/`test_run.py` are touched by 1.1, 1.3 and 1.5, and `test_index.py` by 1.3. Run **1.1 → 1.3 → 1.5** sequentially. 1.2 and 1.4 are independent.

## ⛔ Do Not Restore

1.4 and 1.5 make the pilot **fail louder**:
- a truncated or non-`Message` DGX answer raises `GenerationError`;
- an empty corpus or `--k < 1` is refused;
- a scheme-less URL fails settings validation.

These errors are the INTENDED outcome. DO NOT silence them with a fallback (`or ""`, `getattr(..., default)`, `try/except: pass`, clamping `k`). The only acceptable fix for a failing caller is to correct its input or let the error propagate.

## Fix Units

### Fix Unit 1.1: Append each scored answer to a local JSONL inside the loop; group `run()`'s config
- **Files:** `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/tests/test_run.py`, `.gitignore`
- **Violation pattern (Grep):** `^    overlap: int,$`
- **Expected after fix:** 0 matches (the parameter line goes; the new `RunConfig` field `    overlap: int` has no trailing comma)
- **Reference example:** `run.py:Result` (a frozen dataclass), `run.py:_sha256`
- **HOW TO FIX:**
  1. **Crash copy, written as we go (REVIEW 🔴).**
     - Change `_answer_all` to take a `sink: Path` and, after each `Result` is built, append `json.dumps(asdict(result)) + "\n"` to it. Open with `"a"` and `encoding="utf-8"`, and call `parents=True, exist_ok=True` on the parent once before the loop. `Outcome` is a StrEnum and serialises as its value.
     - A kill, a Ctrl-C, a `GenerationError` at question 17, or an MLflow outage at `log_metrics` now all leave the answers computed so far on disk.
     - Keep `mlflow.log_dict(..., "per_question.json")`: the artifact stays the canonical copy, and the JSONL is the crash copy.
  2. **Group the hashed config.** Add:
     ```python
     @dataclass(frozen=True)
     class RunConfig:
         """What identifies a run's setup; logged as params and covered by config_hash."""
         retrieval: Retrieval
         k: int
         n: int | None
         size: int
         overlap: int
         collection: str
     ```
     The new signature is `run(project, settings, pilot, questions, *, config: RunConfig, answer: Answer, search: Search, results_dir: Path) -> str`. Don't add a wrapper for `answer`/`search`/`results_dir`: they share nothing, and 8 parameters grouped by role is enough. Build `params` from `config`. **The logged param names and values must stay byte-identical** (`retrieval` as `str(...)`), so `config_hash` stays comparable with existing runs. Prove it once with a scratch assertion (old dict == new dict for the same inputs), then delete the scratch.
  3. `_answer_all` gains a sixth parameter (`sink`) — accepted: it is a private helper and the REVIEW "max 5" finding targets `run()` (12 → 8 grouped by role; recorded as Accepted in FIX_PLAN.md).
  4. Inside the `tracked_run` block, the sink is `results_dir / f"{run_id}.jsonl"`. In `main()`, pass `results_dir=project.root / "results"` and `config=RunConfig(...)`.
  5. In `.gitignore`, add `projects/*/results/`.
  6. In `test_run.py`, update `_run()` to build a `RunConfig` and pass `results_dir=tmp_path / "results"`. All existing tests must pass without assertion changes. Add:
     - `test_f_13_mlflow_failure_after_answers_keeps_results_locally`: monkeypatch `mini_rag.run.mlflow.log_metrics` to raise `MlflowException("down")`, then `pytest.raises(MlflowException)`. Exactly one `*.jsonl` exists, it has 4 lines, and the ids are `["q1","q2","q3","q4"]` with line 4's `prediction == "hunter2"`.
     - `test_f_13_generation_error_keeps_earlier_answers`: an `answer` that raises `GenerationError` on q3. The JSONL then has exactly the 2 lines q1 and q2.

### Fix Unit 1.2: Bound MLflow HTTP retries so an outage fails in about a minute, not 15–20 min
- **Files:** `packages/datalab/src/datalab/tracking.py`, `packages/datalab/tests/test_tracking.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (behavioural: proven by `test_tracking_bounds_mlflow_http_retries`)
- **Reference example:** snippet:
  ```python
  _HTTP_DEFAULTS: Final = {"MLFLOW_HTTP_REQUEST_MAX_RETRIES": "2", "MLFLOW_HTTP_REQUEST_TIMEOUT": "30"}

  def _bound_http_retries() -> None:
      """MLflow's defaults (7 retries × 120 s, backoff 2) turn an outage into a ~20 min hang; a user value wins."""
      for key, value in _HTTP_DEFAULTS.items():
          os.environ.setdefault(key, value)
  ```
- **HOW TO FIX:**
  1. Add the snippet to `tracking.py` (import `os`; `Final` from typing). mlflow 3.17.2 reads both variables (`mlflow/environment_variables.py:233,257`).
  2. Call `_bound_http_retries()` as the first line of `preflight()` and of `tracked_run()`.
  3. Tests. The autouse `_isolated` fixture already clears every `MLFLOW_*` variable, so no fixture change is needed.
     - `test_tracking_bounds_mlflow_http_retries`: after `preflight(sqlite_uri)`, `os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "2"`.
     - `test_tracking_keeps_a_user_retry_setting`: `monkeypatch.setenv(..., "5")` first; `"5"` survives.

### Fix Unit 1.3: Key the vector index on corpus content, not chunk count (stale-index reuse)
- **Files:** `projects/mini-rag/src/mini_rag/index.py`, `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/tests/test_index.py`, `projects/mini-rag/tests/test_run.py`
- **Violation pattern (Grep):** `def index_name\(embedder: str, size: int, overlap: int\) -> str:|fake\.calls == \[\("delete"`
- **Expected after fix:** 0 matches
- **Reference example:** `run.py:_sha256` (sorted-keys JSON → sha256)
- **HOW TO FIX:**
  1. In `index.py`, add `def corpus_hash(chunks: list[Chunk]) -> str`. It returns the first 12 hex characters of the sha256 of `json.dumps([[c.chunk_id, c.text] for c in chunks])`.
  2. Change `index_name` to `(embedder: str, size: int, overlap: int, corpus: str)`, returning `collection_name("mini-rag", "t2v", embedder, f"w{size}o{overlap}", f"c{corpus}")`. Update the docstring: "a corpus edit gets a new collection, never stale vectors".
  3. Give `ensure_collection` a keyword-only `corpus: str` parameter and use `index_name(embedder, size, overlap, corpus)`. Keep the count check as a completeness check. In `main()`, compute `corpus = corpus_hash(chunks)` **once** and pass it to both `ensure_collection(..., corpus=corpus)` and `RunConfig`: add a `corpus_hash: str` field there and a `"corpus_hash"` param.
  4. In `test_index.py`:
     - add `test_corpus_content_change_with_same_count_gets_a_new_index`: two equal-length chunk lists, one text differs, so the names differ; the same content gives the same name;
     - update existing call sites with a fixed corpus string;
     - **replace the call-order change detectors** at `test_index.py:106` and `test_index.py:114` (`fake.calls == [("delete", name), ("create", name), ...]`) with outcome checks: the returned name or `pytest.raises(IndexBuildError)`; `sum(op == "create" for op, _ in fake.calls)` equal to the expected build count; and `all(n == name for _, n in fake.calls)` (only our exact name is touched).
  5. In `test_run.py`, pass `corpus_hash="abc123"` in the `RunConfig` and assert `run.data.params["corpus_hash"] == "abc123"`.
  6. PR body: existing collections are orphaned **once** (new names), and every new run's `config_hash` differs from older runs because `corpus_hash` is now a param. Both are intended; delete old collections by exact name in Weavit UI.

### Fix Unit 1.4: Treat a truncated or non-`Message` DGX response as a GenerationError
- **Files:** `projects/mini-rag/src/mini_rag/generate.py`, `projects/mini-rag/tests/test_generate.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (behavioural: proven by the three new `GenerationError` tests)
- **Reference example:** the existing `if not text: raise GenerationError(...)` at `generate.py:71-72`
- **HOW TO FIX:**
  1. After the `messages.create` try block, add `if not isinstance(message, anthropic.types.Message): raise GenerationError(f"dgx {self.model}: malformed response ({type(message).__name__})")`.
  2. Then add `if message.stop_reason == "max_tokens": raise GenerationError(f"dgx {self.model}: answer truncated at max_tokens={self.max_tokens}; raise MINI_RAG_MAX_TOKENS")`.
  3. In `test_generate.py`, the existing `_generator(status, body: dict, seen=None)` helper always sends `json=body`. Add a sibling `_raw_generator(response: httpx2.Response) -> DgxGenerator` that builds the same `MockTransport` client but returns `response` as-is. Then add three tests:
     - `_raw_generator(httpx2.Response(200, content=b"<html>"))` raises `GenerationError`;
     - `_raw_generator(httpx2.Response(200, json=[1, 2]))` raises `GenerationError`;
     - `_generator(200, {**_message([{"type": "text", "text": "50"}]), "stop_reason": "max_tokens"})` raises `GenerationError` matching `"truncated"`.

     If the SDK already raises `anthropic.APIResponseValidationError` (an `APIError`) on the first two, the existing `except` catches it. Keep the tests either way.

### Fix Unit 1.5: Fail fast on bad input: empty corpus, `--k < 1`, scheme-less URLs; CLI tests
- **Files:** `projects/mini-rag/src/mini_rag/corpus.py`, `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/src/mini_rag/settings.py`, `packages/datalab/src/datalab/settings.py`, `projects/mini-rag/tests/test_corpus.py`, `projects/mini-rag/tests/test_settings.py`, `packages/datalab/tests/test_settings.py`
- **New files:** `projects/mini-rag/tests/test_cli.py`
- **Violation pattern (Grep):** `parser\.add_argument\("--k", type=int,`
- **Expected after fix:** 0 matches (`--k` uses a bounded type)
- **Reference example:** `run.py:_select` (refuses, never clamps)
- **HOW TO FIX:**
  1. `corpus.py` `load_corpus`: build the list, then `if not chunks: raise ValueError(f"corpus folder {folder} has *.md files but no text to index")`.
  2. `run.py`: `def _positive_int(text: str) -> int` raises `argparse.ArgumentTypeError` for values below 1. Use `type=_positive_int` for `--k`.
  3. URL fields: `dgx_base_url` in `mini_rag/settings.py` and `mlflow_tracking_uri` in `datalab/settings.py`. Add a `field_validator` that raises `ValueError(f"... must be a URL with a scheme, e.g. http://host:port, got {v!r}")` unless `"://" in v`, and keep the type as `str`. Do **not** use `urlsplit(v).scheme`: `urlsplit("dgx.lan:8000").scheme == "dgx.lan"`, so it would accept the bad value. Do **not** allowlist schemes either: MLflow also accepts `sqlite:////…`, `postgresql://`, `mysql://`, and so on, which all contain `://`.
  4. Tests:
     - `test_corpus_with_only_empty_files_raises` (`a.md` holds `"\n  \n"`);
     - `test_scheme_less_dgx_url_fails_at_settings` (`"dgx.lan:8000"` raises `ValidationError`);
     - `test_scheme_less_tracking_uri_fails_at_settings` (`"127.0.0.1:5050"`).

     Confirm that the `sqlite_uri` fixture value still validates.
  5. New `tests/test_cli.py`:
     - `test_k_below_one_is_refused`: `_args(["--retrieval", "bm25", "--k", "0"])` raises `SystemExit`;
     - `--retrieval bogus` raises `SystemExit`;
     - a missing `--k` raises `SystemExit`;
     - valid args parse to `Retrieval.BM25` and `k == 3`, with `n` `None` when omitted;
     - `test_f_13_main_validates_config_before_io`: monkeypatch `mini_rag.run.load` to `lambda: Project("mini-rag", tmp_path)`. Keep `_isolated`'s tmp cwd and **never chdir into the real `projects/mini-rag`**, because its local `.env` sets `MINI_RAG_DGX_BASE_URL` and would make the test pass on CI but fail locally. Monkeypatch `mini_rag.run.preflight` and `mini_rag.run.connect_weaviate` to `pytest.fail("I/O before config")`. Then `main(["--retrieval", "bm25", "--k", "3"])` must raise `ValidationError`.

<!-- plan-validate: READY 2026-11-04 sha256:1d3a41b18fe3 -->
