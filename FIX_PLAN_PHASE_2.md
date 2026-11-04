# Fix Plan — Phase 2: Gates, input validation & dependency hygiene

**Severity:** 🟡
**Agent:**
- python-fastapi for 2.1, 2.4 and 2.5. This is generic Python: ignore the FastAPI layering rules.
- general-purpose for 2.2 and 2.3 (CI YAML and pre-commit config; no source code).

**Depends on:** none (independent of Phase 1; merge order between 1 and 2 is free)
**Fix units:** 5
**Files affected:** 11

Baseline, measured 2026-11-04 **before Phase 1**. Every gate wired here was green then. If Phase 1 has merged first, re-run the four commands below before wiring them, and fix any new finding inside this phase:
- `uv run --locked lint-imports`: 1 contract kept in each of `packages/datalab` and `projects/mini-rag`;
- `uv run --locked pyright`: 0 errors in both;
- `uv run --locked pip-audit`: no known vulnerabilities (the local dists `datalab`/`proj-mini-rag` are reported as skipped, which is expected);
- `npm audit --audit-level=moderate` in `app`: 0.

## Within-phase Dependencies

- 2.2 → 2.3: 2.3's pre-push hooks mirror the CI commands 2.2 settles, and both edit `.pre-commit-config.yaml`.
- 2.4 → 2.5: 2.5 copies 2.4's dependency specs into the template.
- 2.1 is independent. Its test change is committed **red first**, then the fix.

## Fix Units

### Fix Unit 2.1: Project names: `fullmatch` instead of `^…$` + `.match` (trailing-newline bypass)
- **Files:** `packages/datalab/src/datalab/project.py`, `contracts/name_vectors.json`
- **Violation pattern (Grep):** `NAME_RE\.match\(`
- **Expected after fix:** 0 matches
- **Reference example:** the JS twin `app/src/lib/name.ts`. JS `$` without the `m` flag does not match before a trailing `\n`, so it already rejects; the fix aligns Python with it.
- **HOW TO FIX:**
  1. **Red first.** In `contracts/name_vectors.json`, append `"a\n"`, `"mini-rag\n"`, `"a\r"`, `"mini-rag\r\n"` to `reject` as JSON escapes.
     - `uv run pytest tests/test_project.py -k f_12` in `packages/datalab` must **fail** on `"mini-rag\n"`.
     - `npm test` in `app` must stay **green**.

     Commit as `test: shared name vectors reject line terminators (red)`.
  2. In `project.py`, keep the `NAME_RE` literal (line 13) identical to `name.ts`. Change the three call sites at lines 35, 101 and 122 to `NAME_RE.fullmatch(x)`.
  3. Extend the comment on line 12: `# Identical literal in app/src/lib/name.ts; Python uses fullmatch (its "$" also matches before a final "\n").`
  4. Both suites are green. `validate_name("mini-rag\n")` raises `ProjectError`.

### Fix Unit 2.2: CI: full-history secrets scan, contracts/types/dep-audit gates, locked syncs
- **Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
- **Violation pattern (Grep):** `uv sync &&`
- **Expected after fix:** 0 matches
- **Reference example:** target shape of the Python steps:
  ```yaml
      - name: mini-rag gates (contracts, types, deps) + unit tests + coverage floor
        run: |
          uv sync --locked
          uv run --locked lint-imports
          uv run --locked pyright
          uv run --locked pip-audit
          uv run --locked pytest --cov
  ```
- **HOW TO FIX:**
  1. **Secrets (gitleaks).**
     - The pre-commit hook runs `gitleaks git --pre-commit --staged`, and `pre-commit run --all-files` on a fresh checkout has nothing staged, so in CI it scans nothing.
     - In job `checks`, set `fetch-depth: 0` on checkout and add a step `secrets scan (whole history; the pre-commit hook only sees staged files)`:
       ```
       curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz | tar -xz gitleaks
       ./gitleaks git --redact --verbose .
       ```
       That is the same version as `.pre-commit-config.yaml`; add `# keep in sync with .pre-commit-config.yaml gitleaks rev` next to the URL, and the matching comment on the hook, so a bump touches both. Don't use `gitleaks-action`: it needs a licence key for orgs.
     - In `.pre-commit-config.yaml`, add `# CI: this hook scans staged files only; ci.yml runs a full-history scan` above the gitleaks hook.
     - Run `gitleaks git --redact .` locally. It must exit 0. If it finds anything, **stop and report**; never allowlist without the user.
  2. **Python gates.** In job `checks`, replace `uv sync && uv run pytest --cov=datalab` with the five-line block above (`pytest --cov=datalab`), and rename the step "datalab gates + unit tests + coverage floor". Make the same change in job `pilot`.
  3. Check that `pip-audit` exits 0 when it only skips local dists: run `uv run --locked pip-audit; echo $?` in both trees. If it doesn't, use `--skip-editable` and note why in a YAML comment.
  4. **App.** In job `app`, after `npm ci`, add `npm audit --audit-level=moderate`.
  5. Line 1 comment: describe what CI runs versus the local hooks of 2.3. Today it wrongly claims pre-push parity.

### Fix Unit 2.3: Local pre-push parity: the same gates and tests before push
- **Files:** `.pre-commit-config.yaml`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (additive: three `stages: [pre-push]` hooks — datalab, mini-rag, app)
- **Reference example:** the existing `declared-deps` local hooks (`language: system`, `pass_filenames: false`)
- **HOW TO FIX:**
  1. Add three local hooks. All use `language: system` and `pass_filenames: false`:
     - `gates-datalab`, `stages: [pre-push]`, `files: ^(packages/datalab/|contracts/)`, entry `bash -c 'cd packages/datalab && uv run --locked lint-imports && uv run --locked pyright && uv run --locked pytest -q --cov=datalab'`;
     - `gates-mini-rag`, `stages: [pre-push]`, `files: ^(projects/mini-rag/|packages/datalab/src/)`, the same shape with `pytest -q --cov`;
     - `gates-app`, `stages: [pre-push]`, `files: ^(app/|contracts/|\.env\.example$)`, entry `bash -c 'cd app && npm run check && npm test'`.

     pip-audit and the gitleaks history scan stay CI-only because they need the network. Say so in a comment.
  2. Add `default_install_hook_types: [pre-commit, pre-push]` at the top, so `pre-commit install` wires both stages.
  3. `pre-commit install && pre-commit run --hook-stage pre-push --all-files`: all three pass.

### Fix Unit 2.4: Bound the floating runtime dependency specs
- **Files:** `packages/datalab/pyproject.toml`, `projects/mini-rag/pyproject.toml`, `packages/datalab/uv.lock`, `projects/mini-rag/uv.lock`
- **Violation pattern (Grep):** `"(pydantic-settings|httpx)>=[0-9.]+"|"pyyaml>=6\.0",$`
- **Expected after fix:** 0 matches (the `$` excludes `projects/mini-rag/pyproject.toml:23`, the dev-group `"pyyaml>=6.0",  # …` line, which has a trailing comment and stays as-is)
- **Reference example:** the exact runtime pins already present (`"weaviate-client==4.24.1"`, `"mlflow==3.17.2"`)
- **HOW TO FIX:**
  1. For each matched **runtime** spec (pydantic-settings in both trees, pyyaml and httpx in datalab), read the version resolved in that tree's `uv.lock`. Write a compatible-release bound on the locked minor; for example, pydantic-settings is locked at 2.16.2 in both trees, so it becomes `"pydantic-settings~=2.16"`.
  2. **Dev-group `>=` specs stay as they are** (user decision 2026-11-04): `uv.lock` is their pin, CI runs `--locked`, and `uv lock --upgrade` keeps working. This is recorded in FIX_PLAN.md.
  3. Run `uv lock` in each tree. Resolved versions must **not** move: `git diff */uv.lock` shows only specifier metadata. If a version moves, the bound is wrong.
  4. `uv sync --locked && uv run pytest` in both trees: green.

### Fix Unit 2.5: The project template inherits the gates and the Python pin
- **Files:** `templates/project/pyproject.toml`, `packages/datalab/tests/test_new_project.py`
- **New files:** `templates/project/.python-version`
- **Violation pattern (Grep):** `dev = \["pytest>=8"\]`
- **Expected after fix:** 0 matches
- **Reference example:** `projects/mini-rag/pyproject.toml` and `packages/datalab/.python-version`
- **HOW TO FIX:**
  1. Copy these from mini-rag into the template:
     - the `[dependency-groups] dev` list (pytest, pytest-cov, pyright, ruff, pip-audit; **not** import-linter, see below);
     - `[tool.ruff] extend = "../../ruff.toml"`;
     - `[tool.pytest.ini_options]` with the `integration` marker and `addopts = "-ra --strict-markers -m 'not integration'"`;
     - `[tool.coverage.run] branch = true` and `[tool.coverage.report] fail_under = 70`;
     - `[tool.pyright]` (`include = ["src", "tests"]`, `venvPath`/`venv`).

     Don't copy `[tool.importlinter]`: a new project has no contract, and an empty contract list fails `lint-imports`.
  2. Create `templates/project/.python-version` containing `3.12`. IMPLEMENTATION_NOTES Phase 2A records that uv otherwise builds new projects on 3.14 while CI runs 3.12.
  3. In `test_new_project.py`, extend the scaffold test that reads `pyproject["project"]["name"]` (line ~39):
     - assert `(fake_repo/"projects"/"demo"/".python-version").read_text().strip() == "3.12"`;
     - assert `pyproject["tool"]["coverage"]["report"]["fail_under"] == 70`.

     `fake_repo` copies the real template (`packages/datalab/tests/conftest.py:41`, `shutil.copytree(TEMPLATE, template)`), so the new `.python-version` is picked up with no fixture change.

<!-- plan-validate: READY 2026-11-04 sha256:66042d7fd82a -->
