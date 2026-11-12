# Fix Plan — Phase 2: Python lint, hooks & docs

**Severity:** 🟡
**Agent:** python-fastapi (this repo is NOT a FastAPI app: ignore that agent's router/service/repository layer rules; apply its Python typing, tooling and documentation rules only)
**Depends on:** Phase 1 (shares test files; 2.3d turns on ruff rules that Phase 1's new code must already satisfy)
**Fix units:** 13
**Files affected:** 40

Context: data-lab is a uv monorepo (Python 3.12) with one root `ruff.toml`, a root `pyrightconfig.json` (covers `tools/` + `tests/`, the `gates-root` pre-push hook) and per-tree `pyproject.toml` pyright configs (`strict = ["src"]`). Vendored harness-recipe scripts live in `tools/pre_commit_checks/` (`_base.py`, `_layout.py`, `check_declared_dependencies.py`, `check_enum_discipline.py`, `check_function_length.py`); `_layout.py` is byte-identical to its recipe and stays untouched (decision #41); `tools/check_hydra_project.py` is vendored verbatim (sha256 header) — never edit it. The authoritative gate is `pre-commit run --all-files --hook-stage pre-push`. Use the repo's ruff: `packages/datalab/.venv/bin/ruff` (0.17.3). ADRs go in `decisions.md` (`## YYYY-MM-DD — Title`, then **Status / Context / Decision / Alternatives considered / Consequences**). `packages/datalab/tests/test_ledger_transitions.py` reads the five `status + decision → status` lines of ARCHITECTURE.md — never reword them.

## Within-phase Dependencies

Run in this order (each line may run its own units in any order):
1. 2.1a, 2.1b, 2.1c — justify suppressions.
2. 2.2 — suppression hook (edits `.pre-commit-config.yaml`).
3. 2.4a, then 2.4b — shrink `check_enum_discipline.py`, then widen the size hooks (edits `.pre-commit-config.yaml` after 2.2, and `tools/check_file_size.py`).
4. 2.3a, 2.3b, 2.3c — N818 renames (2.3a before 2.3b: both edit `sweep.py`, `test_runner.py`, `ARCHITECTURE.md`).
5. 2.3d — ruff config (needs 2.3a–c done, or N818 fails).
6. 2.3e — pyright strict on project-owned tools files (after 2.4b, which edits `check_file_size.py`).
7. 2.5, then 2.6 — docs and ADRs describe everything above.

## Fix Units

### Fix Unit 2.1a: Justify suppressions — datalab, mini-rag, template, tools
- **Files:** `packages/datalab/tests/test_integration.py`, `packages/datalab/tests/test_settings.py`, `projects/mini-rag/tests/test_generate.py`, `projects/mini-rag/tests/test_settings.py`, `templates/project/tests/test_eval.py`, `tools/pre_commit_checks/check_declared_dependencies.py`
- **Violation pattern (Grep):** `#\s*(type|pyright):\s*ignore\[[^\]]*\]\s*$`
- **Expected after fix:** 0 matches
- **Reference example:** the repo's convention `# noqa: S603  # fixed argv, no shell` — the rule code, then `  # ` and a short WHY.
- **HOW TO FIX:**
  1. For each matching line append `  # <why>` after the bracket. Reasons: Settings `_env_file=` → `# _env_file is a pydantic-settings init kwarg the type stub omits`; `httpx2.Client(transport=…MockTransport…)` / `http_client=client` → `# httpx2 stub types the transport/client narrower than its runtime`; `tomllib = None` / `packages_distributions = None` → `# optional import fallback`; `.lifecycle_stage` → `# get_experiment_by_name returns Optional; the experiment was created above`; template `split["splits"] = …` → `# TypedDict field narrowed by the test on purpose`.
  2. Never widen a code. Append the reason on the same line even if it passes 120 chars: ruff 0.17.3 does not report E501 on a line carrying a `# type: ignore[...]` / `# pyright: ignore[...]` pragma (measured).

### Fix Unit 2.1b: Justify suppressions — voice-arch src + top-level tests
- **Files:** `projects/voice-arch/src/voice_arch/live_caller.py`, `projects/voice-arch/src/voice_arch/llm_guard.py`, `projects/voice-arch/src/voice_arch/sweep.py`, `projects/voice-arch/src/voice_arch/worker.py`, `projects/voice-arch/tests/test_audio.py`, `projects/voice-arch/tests/test_caller.py`, `projects/voice-arch/tests/test_llm_guard.py`, `projects/voice-arch/tests/test_settings.py`
- **Violation pattern (Grep):** `#\s*(type|pyright):\s*ignore\[[^\]]*\]\s*$`
- **Expected after fix:** 0 matches
- **Reference example:** `projects/voice-arch/src/voice_arch/budget.py` — `# pyright: ignore[reportUnknownMemberType]  # PagedList.token`.
- **HOW TO FIX:**
  1. Append `  # <why>`: `room.on(...)` → `# LiveKit's EventEmitter.on is untyped`; `stream._event_ch.output_sent` → `# LiveKit private channel: the only end-of-stream signal`; `mlflow.log_dict(per_conversation, …)` → `# log_dict is typed dict[str, Any]; the payload is a list`; `make_session_report(session).to_dict` → `# LiveKit SessionReport is untyped`; test reads of `_opts` / `_extra_kwargs` → `# asserts the plugin's private config`; `session.llm.chat(...)` → `# llm is Optional on AgentSession; set by the fixture`; `VoiceSettings(_env_file=None)` → the Settings reason from 2.1a.
  2. Same rule as 2.1a: the reason goes on the same line.

### Fix Unit 2.1c: Justify suppressions — voice-arch agent + integration tests
- **Files:** `projects/voice-arch/tests/agents/test_arch_b.py`, `projects/voice-arch/tests/agents/test_confirm_wait.py`, `projects/voice-arch/tests/integration/test_arch_text.py`, `projects/voice-arch/tests/integration/test_one_call.py`, `projects/voice-arch/tests/integration/test_spike.py`
- **Violation pattern (Grep):** `#\s*(type|pyright):\s*ignore\[[^\]]*\]\s*$`
- **Expected after fix:** 0 matches
- **Reference example:** as 2.1b.
- **HOW TO FIX:**
  1. `add_message(role=role, …)` → `# role is a plain str here; LiveKit types it as a Literal`; the three `VoiceSettings(_env_file=(…))` lines → the Settings reason from 2.1a. Reason on the same line.

### Fix Unit 2.2: Enforce the suppression format in pre-commit
- **Files:** `.pre-commit-config.yaml`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `pre-commit run suppression-reason --all-files` passes, and was seen failing once with one reason stripped (then restored).
- **Reference example:** pre-commit's built-in `language: pygrep` (no script needed).
- **HOW TO FIX:**
  1. Add as the first hook of the `local` repo:
     ```yaml
      - id: suppression-reason
        name: type/pyright ignores carry a reason (`# type: ignore[code]  # why`)
        language: pygrep
        entry: '#\s*(type|pyright):\s*ignore\[[^\]]*\]\s*$'
        types: [python]
        exclude: ^tools/(check_hydra_project|pre_commit_checks/_layout)\.py$
     ```

### Fix Unit 2.4a: Shrink `check_enum_discipline.py`
- **Files:** `tools/pre_commit_checks/check_enum_discipline.py`
- **New files:** `tools/pre_commit_checks/enum_maps.py`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `wc -l tools/pre_commit_checks/check_enum_discipline.py` < 200 and the three `enum-discipline*` hooks print the same output before and after (`pre-commit run enum-discipline --all-files`, `…-mini-rag`, `…-voice-arch`).
- **Reference example:** `tools/pre_commit_checks/_base.py` (shared helpers imported by sibling checks through the existing `sys.path.insert`).
- **HOW TO FIX:**
  1. The file is 202 lines because it carries this repo's per-tree StrEnum value maps (the local customisation over the recipe). Move those map constants verbatim into `enum_maps.py` (module docstring: "this repo's per-tree StrEnum value maps for check_enum_discipline") and `from enum_maps import …` them in the checker, next to its existing sibling imports.
  2. No other change to the checker's logic.

### Fix Unit 2.4b: Size hooks cover `tools/`
- **Files:** `.pre-commit-config.yaml`, `tools/check_file_size.py`, `tests/test_check_file_size.py`
- **Violation pattern (Grep):** `files: \^\(packages\|projects\|templates\)/\[\^/\]\+/src/\.\*\\\.py\$`
- **Expected after fix:** 0 matches
- **Done when:** the two new tests in `tests/test_check_file_size.py` pass (seen red first) and `pre-commit run file-size --all-files` + `pre-commit run check-function-length --all-files` pass.
- **Reference example:** `tests/test_check_file_size.py` (existing scope tests).
- **HOW TO FIX:**
  1. In `.pre-commit-config.yaml`, for both `file-size` and `check-function-length`: `files: ^((packages|projects|templates)/[^/]+/src/|tools/).*\.py$` and `exclude: ^tools/(weavit-ui/|check_hydra_project\.py$|pre_commit_checks/_layout\.py$)`; names become "src + tools modules <= 200 lines" and "src + tools functions <= 30 lines, classes <= 150".
  2. `tools/check_file_size.py`: `_in_scope` also returns True for `tools/**/*.py` except `tools/weavit-ui/**`, `tools/check_hydra_project.py`, `tools/pre_commit_checks/_layout.py`; the no-argument glob also walks `tools/**/*.py`; update the module docstring. Put a one-line comment next to the exclusion set: "keep in sync with the file-size / check-function-length `exclude:` in .pre-commit-config.yaml" (and the reverse comment in the yaml).
  3. Tests in `tests/test_check_file_size.py`: `test_tools_module_over_cap_is_reported` (a 201-line file at a temp `tools/x.py`, run `main` from that temp root → returns 1) and `test_vendored_tools_files_are_out_of_scope` (`_in_scope(Path("tools/weavit-ui/a.py"))` and `_in_scope(Path("tools/pre_commit_checks/_layout.py"))` are False).

### Fix Unit 2.3a: Rename internal exceptions (N818) — mini-rag + budget
- **Files:** `projects/mini-rag/src/mini_rag/run.py`, `projects/mini-rag/tests/test_run.py`, `projects/voice-arch/src/voice_arch/budget.py`, `projects/voice-arch/src/voice_arch/sweep.py`, `projects/voice-arch/tests/test_bench.py`, `projects/voice-arch/tests/test_budget.py`, `projects/voice-arch/tests/test_runner.py`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `\bEmptyRetrieval\b|\bBudgetExceeded\b`
- **Expected after fix:** 0 matches
- **Reference example:** `datalab.ledger.LedgerError`, `datalab.project.ProjectError` (the `…Error` suffix N818 asks for).
- **HOW TO FIX:**
  1. Rename `EmptyRetrieval` → `EmptyRetrievalError` and `BudgetExceeded` → `BudgetExceededError` everywhere in the listed files (whole-word replace; definitions, raises, excepts, imports, `pytest.raises`, docs). These are project-internal, not part of `datalab`'s public API.
  2. Run `packages/datalab/.venv/bin/ruff check --fix <edited .py files>` and `packages/datalab/.venv/bin/ruff format <edited .py files>` (longer names can break import sorting or line length), then run the mini-rag and voice-arch gates.

### Fix Unit 2.3b: Rename internal exceptions (N818) — voice-arch call + sweep
- **Files:** `projects/voice-arch/src/voice_arch/call.py`, `projects/voice-arch/src/voice_arch/sweep.py`, `projects/voice-arch/tests/test_call.py`, `projects/voice-arch/tests/test_runner.py`, `tests/TESTING_SCENARIOS.md`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `\bAgentNeverJoined\b|\bLiveKitUnresponsive\b|\bProviderAuthStop\b|\bCallerFaultRate\b`
- **Expected after fix:** 0 matches
- **Reference example:** as 2.3a.
- **HOW TO FIX:**
  1. Whole-word rename: `AgentNeverJoined` → `AgentNeverJoinedError`, `LiveKitUnresponsive` → `LiveKitUnresponsiveError`, `ProviderAuthStop` → `ProviderAuthStopError`, `CallerFaultRate` → `CallerFaultRateError`, in every listed file.
  2. Run `packages/datalab/.venv/bin/ruff check --fix <edited .py files>` and `packages/datalab/.venv/bin/ruff format <edited .py files>` (longer names can break import sorting or line length — e.g. `test_call.py` line 11), then run the voice-arch gate.

### Fix Unit 2.3c: Rename internal exceptions (N818) — winners + test fake
- **Files:** `projects/voice-arch/src/voice_arch/winners.py`, `projects/voice-arch/src/voice_arch/bench.py`, `projects/voice-arch/tests/test_winners.py`, `projects/voice-arch/tests/test_result.py`
- **Violation pattern (Grep):** `\bNoEligibleCandidate\b|\bRateLimited\b`
- **Expected after fix:** 0 matches
- **Reference example:** as 2.3a.
- **HOW TO FIX:**
  1. Whole-word rename: `NoEligibleCandidate` → `NoEligibleCandidateError`; the test-local `RateLimited` → `RateLimitedError`.
  2. Run `packages/datalab/.venv/bin/ruff check --fix <edited .py files>` and `packages/datalab/.venv/bin/ruff format <edited .py files>` (longer names can break import sorting or line length), then run the voice-arch gate.

### Fix Unit 2.3d: Ruff rules ANN, PGH, T20, N
- **Files:** `ruff.toml`
- **Violation pattern (Grep):** `select = \["E", "F", "W", "I", "B", "UP", "S", "SIM", "RUF", "BLE", "PLR0913"\]`
- **Expected after fix:** 0 matches
- **Done when:** `packages/datalab/.venv/bin/ruff check .` exits 0 from the repo root, AND a scaffold-shaped copy passes: `mkdir -p projects/zzdemo/src && cp -r templates/project/src/__DATALAB_PACKAGE__ projects/zzdemo/src/demo && packages/datalab/.venv/bin/ruff check projects/zzdemo; rc=$?; rm -rf projects/zzdemo; test $rc -eq 0`.
- **Reference example:** the existing `[lint.per-file-ignores]` block in `ruff.toml`.
- **HOW TO FIX:**
  1. `select = ["E", "F", "W", "I", "B", "UP", "S", "SIM", "RUF", "BLE", "PLR0913", "ANN", "PGH", "T20", "N"]` and, under `[lint]`, `ignore = ["ANN401"]` with the comment `# Any is allowed with an explanatory comment (house rule, checked in review)`.
  2. Extend `[lint.per-file-ignores]` with exactly these entries (comment above the T20 group: `# CLIs and hooks: their stdout/stderr is the interface`):
     ```toml
     "**/tests/**" = ["S101", "S105", "S106", "PLR0913", "T20"]
     "tools/**" = ["T20"]
     ".claude/archview/**" = ["T20"]
     "packages/datalab/src/datalab/{ledger,new_project,resources}.py" = ["T20"]
     "projects/mini-rag/src/mini_rag/run.py" = ["T20"]
     "projects/voice-arch/src/voice_arch/{bench,decide,dispatch,rate,runner,token}.py" = ["T20"]
     # the template CLIs, and every project scaffolded from them (root ruff.toml is copied into outside workspaces)
     "**/src/*/{eval,prepare,train}.py" = ["T20"]
     # __DATALAB_PACKAGE__ is the placeholder datalab-new renames: not a real module name
     "templates/project/src/__DATALAB_PACKAGE__/__init__.py" = ["N999"]
     # the fakes mirror the Weaviate client's lowercase attribute names (batch, aggregate, query)
     "projects/mini-rag/tests/test_index*.py" = ["N801"]
     # TrackingUnavailable is datalab public API imported by outside workspaces: renaming would break them
     "packages/datalab/src/datalab/tracking.py" = ["N818"]
     ```
     (Replace the existing `"**/tests/**"` line rather than adding a second one.)
  3. Run ruff; if it reports anything else, fix the code (annotate; add a code + reason to a blanket ignore; use `logging` for a print in a non-CLI module) — no new per-file ignores beyond the list above.

### Fix Unit 2.3e: Pyright strict on project-owned tools files
- **Files:** `pyrightconfig.json`, `tools/check_file_size.py`, `tools/pre_commit_checks/hydra_gate.py`, `tools/pre_commit_checks/enum_maps.py`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `pre-commit run gates-root --all-files --hook-stage pre-push` passes.
- **Reference example:** the per-tree `[tool.pyright] strict = ["src"]` in `packages/datalab/pyproject.toml`.
- **HOW TO FIX:**
  1. In `pyrightconfig.json` add `"strict": ["tools/check_file_size.py", "tools/pre_commit_checks/hydra_gate.py", "tools/pre_commit_checks/enum_maps.py"]`. The vendored recipe scripts stay at `basic` (decision recorded in 2.6 item 6) — do NOT edit them for typing.
  2. Fix the strict errors in those three files with types and narrowing (about 4 in `check_file_size.py`, e.g. annotate `too_long: list[str] = []`, `warnings: list[str] = []`). An unavoidable suppression uses the 2.2 format.

### Fix Unit 2.5: ARCHITECTURE.md matches the tree
- **Files:** `ARCHITECTURE.md`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `grep -c value_sets ARCHITECTURE.md` ≥ 1, `grep -c enum_maps ARCHITECTURE.md` ≥ 1, `grep -c suppression-reason ARCHITECTURE.md` ≥ 1, and `uv run --locked pytest -q tests/test_ledger_transitions.py` (in `packages/datalab`) passes.
- **Reference example:** the existing `contracts/` and `tools/` entries in the Project Structure block.
- **HOW TO FIX:**
  1. `contracts/` entry: add `value_sets.json` — "ledger statuses, decisions, kinds and goals; read by `packages/datalab/tests/test_ledger.py` and `app/src/lib/ledger.test.ts`, so the Python enums and the TS `as const` sets cannot drift".
  2. `tools/pre_commit_checks/`: list `check_function_length.py`, `check_declared_dependencies.py`, `check_enum_discipline.py` + `enum_maps.py`, `hydra_gate.py`, `_base.py` / `_layout.py` (vendored harness recipes, except `hydra_gate.py` and `enum_maps.py`). Add `.ci-gate-exemptions.json` at the root ("tracked gate waivers + declared trees for /audit-ci").
  3. Hooks paragraph: add the function-length hook (functions ≤ 30, classes ≤ 150), the `suppression-reason` pygrep hook, and the size-hook scope (`*/src/` + `tools/`, vendored files excluded).
  4. Where the trees are described, add: "Project isolation is structural: each tree has its own uv env (pyright `venv = ".venv"`, no extra paths), so `datalab` cannot import a project and a project cannot import another — pyright, the tests and the declared-deps hook fail on it (ADR 2026-11-11)."

### Fix Unit 2.6: ADRs for six explicit decisions
- **Files:** `decisions.md`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `grep -c "^## 2026-11-11" decisions.md` rises by 6, each new ADR with the five fields.
- **Reference example:** the latest ADR in `decisions.md` (2026-11-11 — Claude plugin).
- **HOW TO FIX:** append six ADRs, all `**Status:** accepted`:
  1. `Project-card status is a hand-edited label, not an FSM` — Context: card `status` (`idée|en cours|conclu|abandonné`) has no transition map; §State Machines already says nothing enforces transitions; Python never reads it, so it is not in `contracts/value_sets.json`. Decision: keep a validated label (membership checked in `app/src/lib/card.ts`), no transition map, no `value_sets.json` entry until a Python reader exists. Alternatives: TRANSITIONS const + git-diff CI check; `card_statuses` in value_sets.json. Consequences: any status change is allowed; revisit if a Python tool reads it.
  2. `Size hooks exclude test files and non-Python files` — Context: 17 test files > 200 lines, test helpers > 30 lines; the hooks cover `*/src/` + `tools/` Python only (app `.ts`/`.astro` sources are all < 200 lines; four small tracked `.sh` scripts). Decision: tests and non-Python files stay out; parametrised scenario tables and fixtures read better together. Alternatives: higher cap for tests; a JS size rule. Consequences: those files can grow unbounded; reviewed by hand.
  3. `Scaffold tests run in CI only` — Context: `pytest -m scaffold` needs the network (`uv lock` against GitHub/PyPI) and is deselected locally (`packages/datalab/pyproject.toml:75`). Decision: keep it CI-only; run `pytest -m scaffold` by hand when touching the template. Alternatives: a manual pre-push stage hook. Consequences: a template break is caught at CI, not at push.
  4. `gates-root dev pins have no separate audit` — Context: `gates-root` pins pyright/pytest/pytest-cov/pyyaml inline; no pip-audit covers that ad-hoc env. Decision: accept — the same four versions are in `packages/datalab/uv.lock`, which CI audits (`ci.yml` pip-audit step); dev tooling only. Alternatives: requirements file + CI pip-audit step. Consequences: if datalab's dev group (`>=`) drifts from the inline pins, the inline ones lose coverage — re-check when bumping pins.
  5. `Project isolation is enforced by per-tree envs, not import-linter` — Context: REVIEW §1 asked for forbidden contracts (datalab ⊥ projects, project ⊥ project). Decision: no contract — each tree's env holds only itself + datalab (pyright `venv = ".venv"`, no extra paths; verified with `find_spec`), so such an import fails pyright, the tests and the declared-deps hook. Alternatives: per-tree `forbidden` contracts naming every other project (to be updated on every new project). Consequences: `templates/project` has no local env — only the CI scaffold test exercises it.
  6. `Pyright strict covers project-owned tools only` — Context: strict on all of `tools/` gives ~84 errors, most in vendored harness-recipe scripts (`check_declared_dependencies.py`, `check_function_length.py`, `check_enum_discipline.py`, `_layout.py`). Decision: strict on `tools/check_file_size.py`, `hydra_gate.py`, `enum_maps.py`; recipe scripts stay `basic` so they keep matching their recipes (same reasoning as #41); test code (root `tests/` and each tree's `tests/`) also stays `basic` — tests use fakes and fixtures that strict mode would force into casts. Alternatives: fix all 84 (recipe drift); strict tests. Consequences: vendored scripts and tests get basic checking; typing fixes for recipes go upstream.

## Verification

After all fix units in this phase complete, every grep pattern in this phase MUST return zero matches. Run `pre-commit run --all-files --hook-stage pre-push`, then `/check`.

<!-- plan-validate: READY 2026-11-11 sha256:0258b78bd08a -->
