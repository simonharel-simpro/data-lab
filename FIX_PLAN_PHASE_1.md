# Fix Plan — Phase 1: Resilience + test quality

**Status:** ✅ Complete (9/9 fix units) — branch fix-phase-1-resilience-tests, 2026-11-11
**Severity:** 🟡
**Agent:** python-fastapi (this repo is NOT a FastAPI app: ignore that agent's router/service/repository layer rules; apply its Python typing, testing and tooling rules only)
**Depends on:** none
**Fix units:** 9
**Files affected:** 20

Context: data-lab is a uv monorepo (Python 3.12). Trees: `packages/datalab` (shared library), `projects/mini-rag`, `projects/voice-arch`, `templates/project` (scaffold template copied by `datalab-new`). Each tree has its own uv env; run its gate from inside the tree: `uv run --locked lint-imports && uv run --locked pyright -p pyproject.toml && uv run --locked pytest -q`. The authoritative gate is `pre-commit run --all-files --hook-stage pre-push` from the repo root. Source modules must stay ≤ 200 lines and functions ≤ 30 lines (pre-commit hooks, scope `packages|projects|templates/*/src/`). Line length 120 (ruff).

Tests are the oracle: never weaken an assertion to go green; every new or rewritten assertion must be seen failing once against the unfixed code (or with the expected value mutated locally, then reverted). Expected values are literals written from the spec, never imported from the code under test.

## Within-phase Dependencies

- 1.1, 1.7 and 1.9 all edit `packages/datalab/tests/test_tracking.py`: run them one after another, in that order.
- 1.2 and 1.4 both touch the template package (`eval.py` / `prepare.py`): run 1.2 before 1.4.
- All other units are independent.

## Fix Units

### Fix Unit 1.1: Bound MLflow HTTP retries on the read path
- **Files:** `packages/datalab/src/datalab/tracking.py`, `packages/datalab/src/datalab/tracking_queries.py`, `projects/voice-arch/src/voice_arch/decide.py`, `packages/datalab/tests/test_tracking.py`, `projects/voice-arch/tests/test_decide.py`
- **Violation pattern (Grep):** `^def _bound_http_retries`
- **Expected after fix:** 0 matches
- **Done when:** `test_query_helpers_bound_mlflow_http_retries` (3 params) and `test_decide_unreachable_mlflow_fails_fast` pass and were seen red first.
- **Reference example:** `tracking.py` `preflight()` and `tracked_run()` both start with `_bound_http_retries()`; `test_tracking_bounds_mlflow_http_retries` in `test_tracking.py` shows how the env var is asserted.
- **HOW TO FIX:**
  1. `tracking.py` imports from `tracking_queries.py` (not the reverse). MOVE `_HTTP_DEFAULTS` (`{"MLFLOW_HTTP_REQUEST_MAX_RETRIES": "2", "MLFLOW_HTTP_REQUEST_TIMEOUT": "30"}`) and the function into `tracking_queries.py`, renamed `def bound_http_retries() -> None:` (public: now used across modules), keeping its docstring. In `tracking.py`, add `bound_http_retries` to the existing `from datalab.tracking_queries import …` line and replace the two `_bound_http_retries()` calls.
  2. In `tracking_queries.py`, call `bound_http_retries()` as the first statement of `project_spend`, `stale_runs` (after its `older_than` check) and `close_runs`.
  3. In `projects/voice-arch/src/voice_arch/decide.py` `main()`: `settings = Settings()`; `try: preflight(settings.mlflow_tracking_uri)` / `except TrackingUnavailable as err: print(f"MLflow unavailable: {err}", file=sys.stderr); return 1` (import both from `datalab.tracking`); then `client = MlflowClient(settings.mlflow_tracking_uri)`. Keep the file ≤ 200 lines (it is 128).
  4. Tests (red first): in `test_tracking.py` add `test_query_helpers_bound_mlflow_http_retries`, parametrised over three callables — `lambda s: project_spend("p", s)`, `lambda s: stale_runs("p", s, timedelta(days=1))`, `lambda s: close_runs("p", s, [])`. Each: `monkeypatch.delenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", raising=False)` and the same for `MLFLOW_HTTP_REQUEST_TIMEOUT`; call with `make_settings(sqlite_uri)`; assert `os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "2"` and `os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "30"` (literals, not `_HTTP_DEFAULTS`). In `projects/voice-arch/tests/test_decide.py` add `test_decide_unreachable_mlflow_fails_fast`: `monkeypatch.setenv("DATALAB_MLFLOW_TRACKING_URI", "http://127.0.0.1:9")`, save `previous = mlflow.get_tracking_uri()` and restore it with `mlflow.set_tracking_uri(previous)` in a `finally` (preflight sets the global URI, which would leak into later tests), call `main()`, assert it returns `1` and `capsys` stderr contains `MLflow unavailable`.

### Fix Unit 1.2: `run.json` writes refuse a stale base
- **Files:** `packages/datalab/src/datalab/ledger.py`, `templates/project/src/__DATALAB_PACKAGE__/eval.py`, `packages/datalab/tests/test_ledger_io.py`, `plugins/datalab/skills/experiment/SKILL.md`
- **Violation pattern (Grep):** `^def write_atomic\(project_dir: Path, ledger: RunLedger, \*, replace_corrupt: bool = False\) -> None:`
- **Expected after fix:** 0 matches
- **Done when:** `test_stale_write_does_not_revert_produce` and `test_write_without_base_keeps_old_behaviour` pass (the first seen red first); `wc -l templates/project/src/__DATALAB_PACKAGE__/eval.py` ≤ 200.
- **Reference example:** `_check_overwrite()` in `ledger.py` (it already reads the current file as `old` before every write).
- **HOW TO FIX:**
  1. Problem: `write_atomic` accepts a ledger computed from an older read, so a stale writer silently reverts `produce`/`decide` (reproduced: status went back to `todo`). The ledger ops rebuild through `revalidate` (`ledger_ops.py:31-35`), so nothing attached to the model survives an op — the base is passed explicitly.
  2. New signature: `def write_atomic(project_dir: Path, ledger: RunLedger, *, base: RunLedger | None = None, replace_corrupt: bool = False) -> None:`. Pass `base` to `_check_overwrite(project_dir, checked, replace_corrupt, base)`; there, insert the check AFTER the whole `try: old = read(project_dir) / except LedgerError: …` block (outside it) and BEFORE the `decisions_log` append-only check: `if base is not None and old != base: raise LedgerError("run.json changed since it was read: re-read it and apply the change again")`. `base=None` keeps today's behaviour.
  3. One comment above that check: the truly simultaneous window (this check, then `os.replace`) stays open and is accepted — data-lab is single-user; this closes the stale-read case. `ledger.py` must stay ≤ 200 lines (it is 182).
  4. Template `eval.py` `_score_test` (line 142) becomes exactly two lines (the file is at 199 lines; a one-line call over 120 chars would be wrapped by ruff and overflow the 200-line cap):
     ```python
         look = ledger.record_test_look(gate.ledger, gate.split_sha, trial_id, gate.look_note)
         ledger.write_atomic(gate.folder, look, base=gate.ledger)
     ```
     Then check `wc -l` ≤ 200; if ruff format still pushes it over, delete one blank line inside a function body (not between top-level definitions).
  5. `SKILL.md` ledger snippet (lines 47-49) becomes exactly:
     ```python
     l = ledger.read(d)
     base = l                         # what was read: write_atomic refuses if run.json changed since
     l = ledger.<op>(l, ...)          # produce / decide / freeze_split / record_data / redo
     ledger.write_atomic(d, l, base=base)
     ```
     `l` keeps its role everywhere else (line 59 rebinds `l = ledger.parse(...)` — fine, `base` is untouched). Add one line after the snippet's closing fence: "A `LedgerError` saying run.json changed since it was read means another writer got there first: re-read and redo the step, never force it." Line 54 (first ledger) becomes: "replace the `read`, `base =` and `<op>` lines with `l = ledger.new_ledger(...)` … and drop `base=base` from the write (there is no file yet)". At lines 128, 135, 151 and 161 append "(with `base=base`)" after `write_atomic`. Line 92 (`new_ledger` + `write_atomic`) gets "(no `base`)"; line 95 (`replace_corrupt=True`) gets "(no `base`: nothing valid to compare against)".
  6. Tests (red first) in `test_ledger_io.py`: `test_stale_write_does_not_revert_produce` — write a ledger whose current milestone is `todo`; `a = read(d)`; `b = read(d)`; `write_atomic(d, produce(a, <m>, [<artifact>]), base=a)`; then `with pytest.raises(LedgerError, match="changed since it was read"): write_atomic(d, b, base=b)`; finally `read(d).milestones[<m>].status is Status.PRODUCED`. `test_write_without_base_keeps_old_behaviour` — the same stale `b` written with no `base` succeeds (documents the opt-in). Do NOT add a "concurrent test look" test: a second stale look is already refused by the append-only rule (`ledger.py:87`), so it cannot go red.

### Fix Unit 1.3: Voice-arch budget counts a cost-unknown run at its estimate
- **Files:** `projects/voice-arch/src/voice_arch/budget.py`, `projects/voice-arch/tests/test_budget.py`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `finished without a cost: key unreadable \(F-12\), counts nothing|!= _FINISHED and "cost_usd" not in`
- **Expected after fix:** 0 matches
- **Done when:** `test_finished_run_tagged_cost_unknown_counts_at_estimate` passes and was seen red first; `test_crashed_run_without_cost_counts_at_the_estimate` and `projects/voice-arch/tests/test_runner.py::test_unreadable_key_tags_cost_unknown` still pass.
- **Reference example:** `_unmeasured_estimates()` in `budget.py` already adds `ESTIMATES_USD[sub]` for non-FINISHED runs with no `cost_usd`.
- **HOW TO FIX:**
  1. Problem: when the OpenRouter `/key` read fails, the sweep only tags `cost_unknown=true`, never logs `cost_usd`, and ends FINISHED — so `spent_so_far` adds $0 and the budget gate never trips.
  2. In `_unmeasured_estimates`, replace the condition with: `"cost_usd" not in run.data.metrics and (run.info.status != _FINISHED or run.data.tags.get("cost_unknown") == "true")`. Keep the warning; make it say "no cost_usd (not finished, or cost unknown)". Update the function docstring the same way.
  3. `test_budget.py`: in `test_crashed_run_without_cost_counts_at_the_estimate`, DELETE the line `_run(client, bench, None, "FINISHED")  # finished without a cost: key unreadable (F-12), counts nothing` (keep `expected` as is — the remaining runs are unchanged). Add `test_finished_run_tagged_cost_unknown_counts_at_estimate`: one FINISHED bench run with no cost and `client.set_tag(run_id, "cost_unknown", "true")` (the `_run` helper has no tags parameter: call `set_tag` on the id it returns), plus one FINISHED bench run with no cost and no tag; assert `spent_so_far(...) == pytest.approx(2.0)` (one bench estimate; 2.0 is already pinned as `ESTIMATES_USD["bench"]` by the existing `(15.0, 2.0)` assertion). Do not write the phrase "counts nothing" anywhere.
  4. `ARCHITECTURE.md` lines 250-252: in the F-12 sentence add "and `spent_so_far` counts that run at its estimate"; in the **Budget:** bullet change "a `voice-arch/<sub>` run that is not FINISHED and logged no `cost_usd`" to "a `voice-arch/<sub>` run that logged no `cost_usd` and is not FINISHED or is tagged `cost_unknown=true`".

### Fix Unit 1.4: Hashed files are byte-stable across platforms
- **Files:** `packages/datalab/src/datalab/ledger_access.py`, `packages/datalab/src/datalab/ledger_checks.py`, `templates/project/src/__DATALAB_PACKAGE__/prepare.py`, `packages/datalab/tests/test_new_project.py`
- **New files:** `templates/project/.gitattributes`, `projects/mini-rag/.gitattributes`, `projects/voice-arch/.gitattributes`
- **Violation pattern (Grep):** `split_sha256\)?"\)?$|differs from run.json data_sha256"\)$`
- **Expected after fix:** 0 matches
- **Done when:** `test_scaffold_ships_gitattributes`, `test_gitattributes_pins_hashed_files` and `test_crlf_split_mismatch_names_line_endings` pass and were seen red first.
- **Reference example:** `templates/project/.gitignore` is a per-project dotfile that `datalab-new` already copies into every new project.
- **HOW TO FIX:**
  1. Problem: `split_sha256` and the data hash use raw bytes; a Windows clone with `core.autocrlf=true` rewrites line endings, the hash changes, and eval refuses with a misleading "tampered" message.
  2. Create `templates/project/.gitattributes`:
     ```
     # run.json pins these by sha256: git must never rewrite their line endings
     split.json -text
     data/** -text
     ```
     Copy it byte-for-byte to `projects/mini-rag/.gitattributes` and `projects/voice-arch/.gitattributes`.
  3. Verify `datalab-new` copies dotfiles from the template (it ships `.gitignore`); if it uses an explicit file list, add `.gitattributes`.
  4. Append the same hint to the three hash-mismatch messages: `ledger_access.py:17` → `"split.json changed since the freeze: its hash differs from run.json split_sha256 (an edit, or git line-ending conversion: see .gitattributes)"`; `ledger_checks.py:30` → put ` — an edit, or git line-ending conversion: see .gitattributes` inside its closing parenthesis; template `prepare.py:85` → `"data_file changed since modeling: its hash differs from run.json data_sha256 (an edit, or git line-ending conversion: see .gitattributes)"`. Use implicit string concatenation if a line exceeds 120 chars. Do NOT touch template `eval.py:84` (it fires when `data_sha256` is None, not on a hash mismatch).
  5. Tests (red first) in `test_new_project.py`: `test_scaffold_ships_gitattributes` — scaffold `demo` the way the neighbouring tests do and assert `(project / ".gitattributes").read_text(encoding="utf-8")` contains `split.json -text` and `data/** -text`; `test_gitattributes_pins_hashed_files` — `subprocess.run(["git", "check-attr", "text", "--", "projects/mini-rag/split.json", "projects/voice-arch/data/x.jsonl"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)` and assert both output lines end with `: text: unset`; `test_crlf_split_mismatch_names_line_endings` — call `ledger.test_access_problem(lg, "0" * 64, None)` on a ledger whose `split_sha256` is another hash (build it the way the existing test-access tests in `packages/datalab/tests` do) and assert the returned message contains `line-ending`. (No existing test asserts the old message text — checked.)

### Fix Unit 1.5: Ledger transition test uses an independent oracle
- **Files:** `packages/datalab/tests/test_ledger_transitions.py`
- **Violation pattern (Grep):** `TRANSITIONS\[\(status, decision\)\]|len\(TRANSITIONS\) == 5`
- **Expected after fix:** 0 matches
- **Reference example:** the spec lines in `ARCHITECTURE.md` §State Machines (`todo + produce → produced`, `produced + produce → produced`, `produced + correct → produced`, `produced + validate → validated`, `produced + redo → todo`).
- **HOW TO FIX:**
  1. Add a module-level literal `_EXPECTED: dict[tuple[Status, Decision | None], Status]` with the five rows above, written by hand (one-line comment: "the spec, ARCHITECTURE.md §State Machines"). Never build it from `TRANSITIONS`.
  2. `test_transitions_table_matches_ops`: same `_PAIRS`; expect `LedgerError` when the pair is not in `_EXPECTED`, else assert the resulting status `is _EXPECTED[(status, decision)]`.
  3. Add `test_transitions_table_is_the_spec`: `assert dict(TRANSITIONS) == _EXPECTED`.
  4. In `test_transitions_table_matches_architecture_md`, iterate `_EXPECTED.items()` instead of `TRANSITIONS.items()` and delete `assert len(TRANSITIONS) == 5`.

### Fix Unit 1.6: Invalid ledger vectors assert what they blame
- **Files:** `packages/datalab/tests/test_ledger.py`, `contracts/run_ledger_vectors.json`
- **Violation pattern (Grep):** `assert str\(caught\.value\)\.startswith\(_expected_prefix\(entry\["rule"\]\)\), name$`
- **Expected after fix:** 0 matches
- **Done when:** every `invalid` vector has the `blames` value from the table, `test_f_18_ledger_vectors` passes, and `cd app && npm test` passes.
- **Reference example:** each invalid vector already has `name`, `rule`, `checked_by`, `run`; `app/src/lib/ledger.test.ts` reads the same file (confirm it ignores unknown keys before editing).
- **HOW TO FIX:**
  1. For every entry under `invalid`, add `"blames": "<value>"` using exactly this `name → blames` table (42 entries; each value is the milestone or field the vector breaks, read from the vector's content against a valid run — the planner checked each against its vector):
     trouvetou-format→kind, unknown-key→notes, missing-dataset-key→dataset, empty-features→features, skipped-status→status, schema-version-2→schema_version, schema-version-true→schema_version, empty-metric→metric, empty-dataset-hash→dataset, split-sha-uppercase→split_sha256, log-missing-note→note, milestone-outside-sequence→milestones, sequence-milestone-missing→milestones, todo-with-decision→dataset, todo-with-artifacts→dataset, validated-with-correct→scoping, produced-with-redo→eda, produced-without-artifacts→eda, produced-after-unvalidated→features, current-not-first-unvalidated→current_milestone, comparison-with-features→features, decision-without-log→scoping, log-decision-mismatch→cleaning, log-unknown-milestone→decisions_log, no-split-hash-after-freeze→split_sha256, dataset-validated-without-dataset→dataset, artifact-escapes→artifact, artifact-absolute→artifact, artifact-backslash→artifact, artifact-drive-letter→artifact, artifact-empty→artifact, winner-before-modeling→winner, modeling-validated-without-winner→winner, second-look-without-note→note, look-sha-uppercase→split_sha256, modeling-without-data-hash→data_sha256, exploration-with-dataset→dataset, exploration-with-split→split_sha256, exploration-with-features→features, exploration-with-winner→winner, exploration-with-data-hash→data_sha256, exploration-with-test-look→test_looks.
  2. Replace the last line of `test_f_18_ledger_vectors` with:
     ```python
         message = str(caught.value)
         assert message.startswith(_expected_prefix(entry["rule"])), name
         assert entry["blames"] in message, name
     ```
  3. Do not re-serialise the file (it holds one vector per line): on each `invalid` line insert `"blames": "<value>", ` right after the `checked_by` array, by text edit.

### Fix Unit 1.7: Drop the redundant tag count
- **Files:** `packages/datalab/tests/test_tracking.py`
- **Violation pattern (Grep):** `len\(contract\["tags"\]\) == 11`
- **Expected after fix:** 0 matches
- **Reference example:** the set-equality assertion just above it in `test_tag_names_match_contract`.
- **HOW TO FIX:**
  1. Delete the `assert len(contract["tags"]) == 11` line; the set equality already pins every tag.

### Fix Unit 1.8: Outside-scaffold source test asserts behaviour, not source layout
- **Files:** `packages/datalab/tests/test_new_project_outside.py`
- **Violation pattern (Grep):** `assert hits == 1`
- **Expected after fix:** 0 matches
- **Reference example:** `test_u1_inside_decided_by_workspace_not_install` asserts on the scaffolded `pyproject.toml` only.
- **HOW TO FIX:**
  1. In `test_f2_outside_source_follows_main`, delete the `src = …`, `hits = …`, `assert hits == 1` lines and `assert DATALAB_GIT_URL == "https://github.com/simonharel-simpro/data-lab"`. Keep `assert SOURCE_LINE in lines` (`SOURCE_LINE` is a literal from the spec — an independent oracle).
  2. Remove imports that become unused (`DATALAB_GIT_URL` stays if another test uses it).

### Fix Unit 1.9: `close_runs` — one behaviour per test, and the unreadable-run path
- **Files:** `packages/datalab/tests/test_tracking.py`
- **Violation pattern (Grep):** `def test_f_9_close_runs_kills_only_given_ids`
- **Expected after fix:** 0 matches
- **Reference example:** `_seed_run` and `make_settings` helpers used by the current test.
- **HOW TO FIX:**
  1. Split the test into `test_f_9_close_runs_refuses_a_finished_run_and_kills_nothing` (`[old, done]` raises `ValueError` matching `done`; `old` stays `"RUNNING"`) and `test_f_9_close_runs_kills_only_the_named_run` (`[old]` returns `[old]`; statuses of `(old, other)` are `["KILLED", "RUNNING"]`).
  2. Add `test_f_9_close_runs_unknown_id_raises_and_kills_nothing`: seed one RUNNING run, call `close_runs("p", make_settings(sqlite_uri), [run, "0" * 32])`, assert `ValueError` matching `cannot be read`, and the seeded run is still `"RUNNING"`.

## Verification

After all fix units in this phase complete, every grep pattern in this phase MUST return zero matches. Run each touched tree's gate, `cd app && npm test` (1.6 edits a shared contract), `pre-commit run --all-files --hook-stage pre-push`, then `/check`.

<!-- plan-validate: READY 2026-11-11 sha256:309fa2f520b2 -->
