# Fix Plan — Phase 4: Test gaps — Python

**Severity:** 🟡
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules. Tests use pytest with AAA layout. Name them `test_<id>_<behaviour>` (or `test_<behaviour>`) and use the existing `conftest.py` fixtures (`fake_repo`, `sqlite_uri`, autouse `_isolated`).
**Depends on:** Phases 1 and 2. They change `run()` (`RunConfig`, `corpus_hash`), the name regex and the template these tests target.
**Fix units:** 8
**Files affected:** 7

**Rules for every unit:**
- **Tests only.** No `src/` change. If a new test exposes a bug, mark it `@pytest.mark.xfail(strict=True, reason="<bug>")`, list it in the PR body, and stop that unit.
- **No new dependency.** Hypothesis is not in the lock. Write property-style checks as exhaustive enumeration over small domains (`itertools.product`) or `@pytest.mark.parametrize` tables.
- **Independent oracles.** Every expected value is a hand-worked literal or a documented derivation. Never recompute it with the module's own helpers (TQ1).

## Within-phase Dependencies

4.2 → 4.3 (both edit `test_scoring.py`). All other units are independent.

## Fix Units

### Fix Unit 4.1: Pin `collection_name` (golden) and the bad-project paths
- **Files:** `packages/datalab/tests/test_project.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** existing `test_u_2_*` / `test_u_3_*` in the same file
- **HOW TO FIX:**
  1. Add `test_collection_name_golden_value` with the comment `# Characterization (TQ8): pins the persisted key format; changing it orphans every Weaviate collection. Captured from v0.1.0.` Assert `collection_name("mini-rag", "t2v", "bge-small-en-v1.5", "w120o20") == "<value>"`, capturing `<value>` once from the current code. A golden value also implies determinism, so no separate determinism test is needed.
  2. Add `test_collection_name_rejects_bad_project` and `test_experiment_name_rejects_bad_project`, parametrized over `["", "A", "mini-rag\n", 3]`, each expecting `ProjectError`.

### Fix Unit 4.2: Scoring helpers: tables for `parse_number`, `normalize`, `contains_phrase`
- **Files:** `projects/mini-rag/tests/test_scoring.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `projects/mini-rag/src/mini_rag/scoring.py:62-100`. Read it first, and write the expectations from its **docstrings and the Demo-RAG intent**, not from running it.
- **HOW TO FIX:**
  1. `parse_number` parametrize table. Each row has a hand-computed value or `None`:
     - plain int;
     - `"1,200"`;
     - `"1.5"`;
     - a negative;
     - every multiplier the module supports (read the list from source);
     - `"$3.2 bn"`;
     - `"5 apples"`;
     - a non-number.
  2. `normalize`: curly vs straight apostrophe, NFKC (a full-width digit becomes ASCII), article dropping (`_ARTICLES = {"a", "an", "the"}`, `scoring.py:23`, so `"the port"` → `"port"`), and punctuation. Add an idempotence check `normalize(normalize(s)) == normalize(s)` over the same inputs.
  3. `contains_phrase(haystack, needle)` (`scoring.py:67-69`, token-boundary containment on already-normalised text): `contains_phrase("x", "")` is `False` (the `bool(needle)` guard); `contains_phrase("port 5050", "5050")` is `True`; `contains_phrase("50505", "5050")` is `False` (the docstring's example). Inputs are normalised by callers, so no case-difference row.
  4. No `numbers_equal` symmetry test: it is `math.isclose`, which is symmetric by construction (TQ7).

### Fix Unit 4.3: `metrics()` invariants by exhaustive enumeration
- **Files:** `projects/mini-rag/tests/test_scoring.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** existing `test_u_12_score_formula`
- **HOW TO FIX:**
  1. `test_metrics_invariants_hold_for_every_small_outcome_list`: for `n` in 1..4, loop over `itertools.product(list(Outcome), repeat=n)`. Assert the rates sum to 1 within 1e-9 and `-1 <= score <= 1`. Use the real `as_dict()` keys, read from source. Do **not** assert `rate == count/n`: that re-implements the function (TQ1).
  2. `test_metrics_all_correct` and `test_metrics_all_hallucination`: the extreme scores as hand-computed literals (`score = accuracy - hallucination`, the `scoring.py:1` docstring: all-correct → 1.0, all-hallucination → −1.0).

### Fix Unit 4.4: `run()`: assert every logged param and the full per-question artifact
- **Files:** `projects/mini-rag/tests/test_run.py`
- **Violation pattern (Grep):** `assert '"q4"' in text|assert '"hallucination"' in text`
- **Expected after fix:** 0 matches
- **Reference example:** existing `test_run_logs_project_tag_and_experiment`
- **HOW TO FIX:**
  1. Replace the two `in text` assertions with `data = json.loads(text)`, then assert `data["results"]` equals the full expected list of dicts (`id`, `prediction`, `expected`, `outcome`, `chunk_ids`) for q1–q4. Write it out literally from `_QUESTIONS`, `_ANSWERS` and `_search`; `chunk_ids` is `["d#s0w0", "d#s0w1", "d#s0w2"]` for `k=3`.
  2. Assert the **whole** `run.data.params` dict against a literal: `retrieval`, `k`, `n`, `questions_hash`, `gen_model`, `max_tokens`, `size`, `overlap`, `collection`, `corpus_hash`. MLflow stores params as strings, so `n=None` is logged as the string `"None"`. Paste `questions_hash` as a literal computed once by hand (`sha256(json.dumps(["q1","q2","q3","q4"], sort_keys=True))`).
  3. Add `test_config_hash_changes_with_k_model_and_size`: three runs, each varying one input, give three distinct `config_hash` tags. `_run()` hardcodes `k=3`, `size=120` and the pilot's model, so first give it keyword arguments `k: int = 3`, `size: int = 120`, `gen_model: str = "deepseek-v4-flash"` passed through to `RunConfig`/`PilotSettings`.

### Fix Unit 4.5: `index.search()` unit tests and the failed-objects branch
- **Files:** `projects/mini-rag/tests/test_index.py`
- **Violation pattern (Grep):** `failed_objects: ClassVar`
- **Expected after fix:** 0 matches (both live today: `test_index.py:56` in `_Batch`, `test_index.py:73` in `_Collection.batch`)
- **Reference example:** the `_FakeCollections` fake in the same file (`test_index.py:40-80`)
- **HOW TO FIX:**
  1. Give the fake's `_Collection` a `query` attribute with `bm25(query, query_properties, limit)` and `near_text(query, limit)`. Each records its call and returns an object whose `.objects` items have `.properties`.
  2. Add `test_search_bm25_maps_objects_to_chunks` and `test_search_vector_uses_near_text`: assert the exact returned `Chunk` list, and that `limit == k`.
  3. `index.py:61` reads `collection.batch.failed_objects`, i.e. the fake's `_Collection.batch.failed_objects` (`test_index.py:73`), **not** `_Batch.failed_objects` (`:56`). Give `_FakeCollections.__init__` a keyword `failed: list[Any] | None = None` stored as `self.failed = failed or []`. In `get()`, set `_Collection.batch.failed_objects` from `fake.failed` and delete the unused `_Batch.failed_objects` line; drop both `ClassVar` annotations (and the `ClassVar` import if now unused). Each failure is an object with a `.message`: `type("Failed", (), {"message": "t2v unreachable"})()`.
  4. Add `test_build_logs_failed_objects`: `_FakeCollections(exists=False, counts=[3], failed=[<that object>])`, call `ensure_collection(...)`. With `caplog`, the warning names the collection and contains `"t2v unreachable"`.

### Fix Unit 4.6: `datalab-new`: a real failure condition, not a patched private helper
- **Files:** `packages/datalab/tests/test_new_project.py`
- **Violation pattern (Grep):** `monkeypatch\.setattr\(new_project, "_rewrite"`
- **Expected after fix:** 0 matches
- **Reference example:** `packages/datalab/src/datalab/new_project.py:21-37` (the leftover-placeholder `ProjectError`)
- **HOW TO FIX:**
  1. Rewrite `test_f_8_failed_copy_leaves_no_project_dir`. Write a stray `__DATALAB_UNKNOWN__` into a file of `fake_repo/"templates"/"project"`. `main(["x"], root=fake_repo)` returns 1 through the `unreplaced … placeholder` `ProjectError`. Assert `projects/` holds neither `x` nor `.x.tmp-*`. Then remove the stray file, run again, and assert success.
  2. Add `test_binary_template_file_is_copied_unchanged`: put `b"\xff\xfe\x00"` in a template file; after `main`, the copied bytes are identical.

### Fix Unit 4.7: Corpus chunking boundaries and the empty-folder error
- **Files:** `projects/mini-rag/tests/test_corpus.py`
- **Violation pattern (Grep):** `"w150" in c\.text\.split\(\) or "Section A" in c\.text`
- **Expected after fix:** 0 matches
- **Reference example:** `projects/mini-rag/src/mini_rag/corpus.py` (`_windows`, `chunk_doc`, `load_corpus`)
- **HOW TO FIX:**
  1. Replace the selector in `test_chunking_overlap_and_ids_stable` with a chunk-id prefix filter (`c.chunk_id.startswith("<doc>#s<k>")`). Use the real doc and section index, read from the test's fixture text.
  2. Add a boundary table on `chunk_doc("d", " ".join(f"w{i}" for i in range(n)), size=10, overlap=2)`. The expected window count is hand-computed from "advance by size − overlap until start + size ≥ n": `n=1 → 1`, `9 → 1`, `10 → 1`, `11 → 2`, `18 → 2`, `19 → 3`. Assert the first and last words of the last window.
  3. Check coverage for those `n`: the union of window words equals all words, and consecutive windows share exactly `overlap` words.
  4. Add cases for `overlap=0`, `overlap=size` (raises `ValueError`), and `test_load_corpus_without_md_files_raises` (an empty `tmp_path` raises `ValueError` matching `"no \*.md"`).
  5. Empty and CRLF documents (REVIEW §4 corpus row):
     - `chunk_doc("d", "")` and `chunk_doc("d", "  \n\n ")` both return `[]`, because whitespace-only sections are skipped at `corpus.py:44-45`;
     - `test_crlf_doc_splits_sections_like_lf`: `chunk_doc("d", "intro\r\n## A\r\nw1 w2\r\n## B\r\nw3")` and the same text with `\n` give identical `chunk_id` and `text` lists, because `_sections` normalises `\r\n` at `corpus.py:21`. Write the expected list literally: `["d#s0w0", "d#s1w0", "d#s2w0"]`.

### Fix Unit 4.8: Port parity across all three `.env.example` copies
- **Files:** `packages/datalab/tests/test_settings.py`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** existing `test_g_10_ports_agree_everywhere` (`test_settings.py:61`)
- **HOW TO FIX:**
  1. Add `test_g_10_env_examples_agree`: parse `.env.example`, `templates/project/.env.example` and `projects/mini-rag/.env.example` as `KEY=value` lines, skipping blanks and comments. Every `DATALAB_*` key must have the same value in all three. Locate the repo root the way the existing g_10 test does.
  2. Split `test_g_10_ports_agree_everywhere`'s docker-gated compose half into its own test, so the settings↔env half never reports SKIPPED. Keep the assertions identical, only move them.

<!-- plan-validate: READY 2026-11-04 sha256:03d4eb0ab9af -->
