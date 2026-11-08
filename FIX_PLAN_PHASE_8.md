# Fix Plan — Phase 8: CI gates & tooling

**Severity:** 🟡
**Agent:** python-fastapi. This is generic Python: ignore the FastAPI layering rules. CI YAML and pre-commit config are part of 8.1.
**Depends on:** none (independent of every other phase)
**Fix units:** 2
**Files affected:** 7 existing (+ 3 new)
**References:** #7 (no root uv project, ADR 3). This phase gives `tools/` a type and test gate **without** a root project, so #7 stays open for its root-gate question only. Comment on #7 with the PR link.

`tools/` + root `tests/` is a Python tree with no uv project. It runs on `uvx` with exact versions, as the CI `root compose test` step already does. Measured on 2026-11-08: `uvx pyright==1.1.414` at the root (root `pyrightconfig.json`, basic, `tools/` + `tests/`) → 0 errors.

## Within-phase Dependencies

8.1 → 8.2: 8.2's tests run under the gate that 8.1 adds.

## Fix Units

### Fix Unit 8.1: A type + test + coverage gate for `tools/` (REVIEW §7 row 2)
- **Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `pyrightconfig.json`, `.ci-gate-exemptions.json`, `packages/datalab/tests/test_hydra_gate.py`
- **New files:** `tests/test_check_file_size.py`, `tests/test_hydra_gate.py` (moved from `packages/datalab/tests/`), `.coveragerc`
- **Violation pattern (Grep):** `run: uvx pytest tests/$`
- **Expected after fix:** 0 matches
- **Reference example:** `packages/datalab/tests/test_hydra_gate.py:14-21` loads the script **in-process** with `importlib.util.spec_from_file_location` and calls its functions. In-process tests are what coverage can see, and subprocess runs are invisible to it (S-3).
- **HOW TO FIX:**
  1. Tests: `tests/test_check_file_size.py` loads `tools/check_file_size.py` in-process and calls `main([...])` with paths under `tmp_path` (monkeypatch `chdir`): a 201-line `packages/x/src/m.py` → 1, with its name on stderr; 200 lines → 0; a file outside `*/src` is ignored. The vendored `tools/pre_commit_checks/{_base,_layout,check_declared_dependencies}.py` are harness recipe code, so they are not tested here.
  2. `.pre-commit-config.yaml`: a pre-push hook `gates-root` that runs pyright and pytest **in one ad-hoc env**, so that pyright resolves `import pytest` / `import yaml` from the tests, and the moved `test_hydra_gate.py` finds `yaml`. Hook settings: `pass_filenames: false`, `stages: [pre-push]`, in the `gates-datalab` hook's shape:
     ```
     entry: bash -c 'uv run --no-project --python 3.12 --with pyright==1.1.414 --with pytest==9.2.0 --with pytest-cov==7.1.0 --with pyyaml==6.0.3 sh -c "pyright && pytest -q tests/ --cov=tools --cov-report=term-missing --cov-fail-under=70"'
     ```
     The pins match voice-arch's dev group; `pyyaml==6.0.3` is the version locked in `packages/datalab/uv.lock`. Point pyright at that env: add `"venvPath"`/`"venv"` only if the `uv run` interpreter is not picked up on its own. Otherwise run it as `python -m pyright`, which uses the running interpreter. Check that `pyright` reports 0 errors with `tests/` resolving `pytest` and `yaml`. Check also that `tests/test_compose.py` still runs in this env (it uses `yaml`). **This hook is the single place the command and pins live** (S-11).
  3. `ci.yml`, job `checks`: replace the `root compose test` step's `run: uvx pytest tests/` with `- name: root tree (tools/ + tests/): types, tests, coverage floor (#7: no root uv project)` / `run: uvx pre-commit run gates-root --hook-stage pre-push --all-files`. The new root `.coveragerc` sets `[run] source = tools` and `omit = tools/check_hydra_project.py, tools/pre_commit_checks/_base.py, tools/pre_commit_checks/_layout.py, tools/pre_commit_checks/check_declared_dependencies.py, tools/weavit-ui/*` (vendored). The measured set is `check_file_size.py` + `pre_commit_checks/hydra_gate.py`. Root tests reach `hydra_gate.py` only if they import it, so move `packages/datalab/tests/test_hydra_gate.py` to `tests/test_hydra_gate.py` (it loads the script by path; compute `REPO_ROOT` locally instead of importing the datalab `tests.conftest`). If the floor fails at 70, add tests: do not lower the floor.
  4. `pyrightconfig.json`: keep basic. Make the include explicit: `"include": ["tools", "tests"]`, keeping the existing `exclude`.
  5. Update `.ci-gate-exemptions.json`: the `pytest` exemption for root `.` (#7) is now covered by this step; leave the `ruff` / `lint-imports` entries.

### Fix Unit 8.2: Size gate warn band; Hydra gate subprocess bounded and its diagnostics on stderr (REVIEW Harness Gap 2; §2 🔵 `hydra_gate` print; §6 🔵 Hydra timeout)
- **Files:** `tools/check_file_size.py`, `tools/pre_commit_checks/hydra_gate.py`
- **New files:** `tests/test_check_file_size.py`, `tests/test_hydra_gate.py` (both created or moved by 8.1; extended here)
- **Violation pattern (Grep):** `print\(f"(skip|hydra-gate) \{rel\}`
- **Expected after fix:** 0 matches
- **Reference example:** `check_file_size.py`'s own `print(line, file=sys.stderr)`.
- **HOW TO FIX:**
  1. `check_file_size.py`: `WARN_LINES = 190`. Any in-scope file with `WARN_LINES ≤ n ≤ MAX_LINES` prints `warning: {path}: {n} lines (cap {MAX_LINES}): split before adding` to stderr. The exit code is unchanged (advisory, never a failure). Test: a 195-line file → exit 0 and the warning is on stderr.
  2. `hydra_gate.py:45,47`: `print(..., file=sys.stderr)` for both diagnostic lines. `subprocess.run(..., check=False, timeout=GATE_TIMEOUT_S)` with `GATE_TIMEOUT_S: Final = 120`; a `subprocess.TimeoutExpired` prints `hydra-gate {rel}: timed out after 120 s` to stderr and returns `False`. Test in the moved `tests/test_hydra_gate.py`: monkeypatch `GATE_TIMEOUT_S` to 0.01 with a gate stub that sleeps, and assert that the check fails with the timeout message.

## Verification

- CI `checks` job green with the new step; `pre-commit run gates-root --hook-stage pre-push` green locally.
- Both patterns → 0 in their files.
- `/check`.

<!-- plan-validate: READY 2026-11-08 sha256:48dbee5965cb -->
