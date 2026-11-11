# Phase 1 — Standalone `datalab`: workspace marker, packaged resources, `datalab-new` outside data-lab

**Agent:** `python-fastapi` (Python 3.12, uv; tree `packages/datalab`, gate `gates-datalab`). **Depends on:** nothing.
**Plan:** `IMPLEMENTATION_PLAN_PLATFORM.md`. **Produces for Phase 2:** `python -m datalab.resources <file>`, root
`datalab.toml`, README §New project with the outside bootstrap.

**Context.** Today `datalab` only works as an editable install from a data-lab checkout: `project.repo_root()` walks up
from the package file to a dir with `packages/datalab` + `compose.yaml` (F-10, no git subprocess); `ledger_model.contract()`
reads `repo_root()/contracts/milestones.json`; `new_project._build` copies `root/templates/project` and `wiring` rewrites
data-lab's `.pre-commit-config.yaml` + `ci.yml`. Goal: `datalab` installed **from git** (`uvx --from
"git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new <name>`) scaffolds a
project in **another repo** (a workspace marked by `datalab.toml`). Inside data-lab nothing changes in behaviour.

**Decisions (from the plan ledger).** D-4 URL constant · D-7 outside source pins the installed commit, else
`branch = "main"` · D-8 contracts/template stay at the repo root, the wheel carries copies via `force-include`, lookup =
checkout for editable installs, package data otherwise · D-9 workspace = nearest regular file `datalab.toml` from the
start path; inside data-lab = that workspace has `packages/datalab/` + `compose.yaml`. D-2: no wiring outside (#48).

Red first: every test below is written and seen failing before its code (ImportError or a targeted mutation).

## Files

#### `datalab.toml` (NEW, repo root)
One comment line: `# data-lab workspace marker (datalab.project.workspace_root); content is ignored.`

#### `packages/datalab/src/datalab/project.py` (MODIFY)
- **Add** `MARKER: Final = "datalab.toml"` and `workspace_root(start: Path | None = None) -> Path`: walk
  `(origin, *origin.parents)` with `origin = (start or Path.cwd()).resolve()`; return the first folder where
  `(folder / MARKER).is_file()` (a directory named `datalab.toml` does not count; content never read). None →
  `ProjectError(f"no {MARKER} found from {origin} up to the filesystem root: create one at your workspace root")`.
- **Add** `is_datalab_checkout(root: Path) -> bool`: `(root/"packages"/"datalab").is_dir() and (root/"compose.yaml").is_file()`.
  Reuse it inside `repo_root()` (same predicate, no duplicate literal).
- **Change** `load(start=None, *, root=None)`: `root = (root or workspace_root(start)).resolve()` (walk from `start`, cwd
  only as the default — U-9). Everything else unchanged (card must sit at `root/projects/<name>/PROJECT.md`).
- **Keep** `repo_root()` exactly (voice-arch `settings.py:20` and resources use it). File stays ≤ 200 lines; if not,
  move the two new functions to a new `datalab/workspace.py` and re-export from `project`.

#### `packages/datalab/src/datalab/resources.py` (NEW, pure: stdlib only; add to the import-linter pure list)
**Purpose:** one place that finds the contracts and the template for both install modes.
- `contract_path(name: str) -> Path`: `name` must be a bare file name present in the contracts folder (no `/`, no
  `..`), else `ProjectError` listing the available names. Folder = `_folder("contracts", "contracts")`.
- `template_dir() -> Path`: `_folder("template", "templates/project")`.
- `_folder(packaged: str, checkout: str) -> Path`: try `repo_root()` → `root / checkout` (editable checkout wins, F-7);
  on `ProjectError` → `Path(str(importlib.resources.files("datalab") / packaged))`. If the chosen folder does not exist →
  `ProjectError` naming the path tried. **No fallback** from one source to the other for a missing file (U-5).
- `main(argv: list[str] | None = None) -> int` + `if __name__ == "__main__"`: `python -m datalab.resources <file>` prints
  the absolute path, rc 0; unknown or path-like name → names listed on stderr, rc 2 (U-10). No other subcommand.

#### `packages/datalab/src/datalab/ledger_model.py` (MODIFY)
`contract()`: `path = contract_path("milestones.json")` (keep the `ProjectError → LedgerError` mapping and `@cache`).
Update the comment on line 19 to say "contracts/milestones.json (via datalab.resources)".

#### `packages/datalab/src/datalab/new_project.py` (MODIFY)
- `DATALAB_GIT_URL: Final = "https://github.com/simonharel-simpro/data-lab"` (the only occurrence in the package, D-4).
- `main`: `root = root or workspace_root()`; `inside = is_datalab_checkout(root)`. Print the resolved workspace in the
  success message (F-5): `created <target> (package <pkg>) in workspace <root>`; keep the current `next:` line text
  (Phase 2 renames `/experiment`).
- `_build`: copy from `template_dir()` (keep `_IGNORE`); after `_rewrite`, if outside call `_render_outside_source(tmp)`;
  call `wiring.plan` **only inside** (F-4); outside, never import-time or call-time touch `.pre-commit-config.yaml`/ci.yml.
- `_render_outside_source(project: Path) -> None`: in `pyproject.toml` replace the exact line
  `datalab = { path = "../../packages/datalab", editable = true }` by
  `datalab = { git = "<DATALAB_GIT_URL>", subdirectory = "packages/datalab", rev = "<sha>" }` when `_installed_commit()`
  returns a sha, else `... branch = "main" }` and print to stderr `datalab: no install commit found, the project
  follows data-lab main` (F-2). Missing line → `ProjectError("template pyproject has no datalab source line")`.
- `_installed_commit() -> str | None`: `importlib.metadata.distribution("datalab").read_text("direct_url.json")` → JSON →
  `vcs_info.commit_id` when it is 40 hex chars; anything else (absent, editable, malformed) → `None`.
- After `os.rename(tmp, target)`, outside only: `_write_workspace_ruff(root)`: copy the packaged/checkout `ruff.toml`
  (resource `contract`-style lookup: `_folder` gives `ruff.toml` from the wheel root copy or the checkout root; add a
  `ruff_toml() -> Path` helper in `resources.py`) with `open(path, "x")` (exclusive create). `FileExistsError` → print
  `kept existing <path>` (F-10, U-7). Never written inside data-lab.
- Outside, after success print `no hook/CI wiring outside data-lab (#48)`.
- `_uv_lock`: `subprocess.run([...], stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0",
  "GCM_INTERACTIVE": "never"}, ...)`; on non-zero exit, if stderr matches (case-insensitive) `could not read username|
  authentication failed|403|404|permission denied|repository not found` → `ProjectError(f"uv lock cannot fetch
  {DATALAB_GIT_URL}: you need read access and git credentials (gh auth setup-git): <last stderr line>")` (F-1).
- Keep functions ≤ 30 lines, file ≤ 200 lines; split rendering into `datalab/new_project_render.py` if needed.

#### `packages/datalab/pyproject.toml` (MODIFY)
```toml
[tool.hatch.build.targets.wheel.force-include]
"../../contracts" = "datalab/contracts"
"../../templates/project" = "datalab/template"
"../../ruff.toml" = "datalab/ruff.toml"
```
The wheel must hold git-tracked files only (U-6): templates/project locally has `.ruff_cache` etc. If force-include
ignores hatch `exclude`, use a wheel `exclude` list matching `_IGNORE` and prove it with the U-6 test on a dirty tree.
Add `datalab.resources` to the pure-modules import-linter contract. A comment states: sdist is unsupported (never
published); build with `uv build --wheel`.

#### `packages/datalab/tests/conftest.py` (MODIFY)
`fake_repo` fixture also writes `datalab.toml`. Add a `workspace` fixture: `tmp_path/"ws"` with `datalab.toml` and an
empty `projects/`, no `packages/datalab`.

#### `templates/project/README.md` (MODIFY)
Replace "datalab comes from ../../packages/datalab" / "repo root" wording: inside data-lab datalab is the editable
`../../packages/datalab`; in another workspace it comes from git (pinned in `uv.lock`). The stack: `docker compose up -d`
in your data-lab checkout (D-6). Keep `/experiment` (Phase 2 renames it).

#### `README.md` (MODIFY, §New project)
Add "In another repo (workspace)": `touch datalab.toml` at its root, then
`uvx --from "git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new <name>`;
needs read access to the private repo + git credentials (`gh auth setup-git`); no hook/CI wiring there yet (#48).

#### `ARCHITECTURE.md` / `decisions.md` (MODIFY)
ARCHITECTURE "Shared package": workspace marker, `resources.py`, inside/outside rule, wheel contents. ADR
"2026-11-10 — Standalone datalab: workspace marker + packaged resources" (context: second dev outside data-lab;
decision D-8/D-9/D-7; alternatives: physical move into `src/datalab` (rejected: app imports, template gate under
datalab strict pyright), "nearest `projects/` dir" (rejected: `~/projects`), release tag (rejected: relocks, tag ritual)).

## Tests (oracle = expected value from the spec)

`packages/datalab/tests/test_project.py` (extend) — keep the F-10 `repo_root` tests unchanged.
| Test | Given → expected | Source |
|---|---|---|
| `test_f5_nearest_marker_wins` | markers at `a/` and `a/b/`, start `a/b/c` → `a/b` | F-5 |
| `test_f5_marker_dir_ignored` | `a/datalab.toml/` is a dir, no other marker → `ProjectError` | F-5 |
| `test_f5_no_marker_raises` | tmp tree without marker → `ProjectError` whose message names the start path | F-5 |
| `test_u8_empty_and_garbage_marker_accepted` | marker content `""` and `"\x00not toml"` → that folder | U-8 |
| `test_u9_workspace_from_start_not_cwd` | cwd in workspace X, `load(Y/projects/p)` with a valid card → project of Y | U-9 |
| `test_is_datalab_checkout` | root with `packages/datalab/` + `compose.yaml` → True; missing either → False | D-9 |

`packages/datalab/tests/test_resources.py` (NEW)
| Test | Given → expected | Source |
|---|---|---|
| `test_f7_editable_prefers_checkout` | real checkout → `contract_path("milestones.json") == REPO_ROOT/"contracts"/"milestones.json"` | F-7 |
| `test_f7_wheel_layout_uses_package_data` | `repo_root` patched to raise, `files("datalab")` patched to tmp pkg with `contracts/milestones.json` → that path | F-7 |
| `test_f7_missing_file_raises` | packaged folder without `value_sets.json` → `ProjectError` naming the packaged path (no checkout fallback) | F-7, U-5 |
| `test_u5_source_tree_has_no_packaged_copies` | `src/datalab/contracts`, `src/datalab/template` → do not exist | U-5 |
| `test_u10_resources_cli` | `["milestones.json"]` → stdout absolute existing path, rc 0; `["../x"]`, `["nope"]` → rc 2, stderr lists `milestones.json` | U-10 |
| `test_u6_wheel_matches_git_ls_files` (`@pytest.mark.scaffold`) | `uv build --wheel` into tmp → `datalab/template/**` == `git ls-files templates/project`, `datalab/contracts/*` == `git ls-files contracts`, `datalab/ruff.toml` present | U-6, S-2 |

`packages/datalab/tests/test_new_project.py` (extend; inject `lock`, never the network; `root=` the fixture)
| Test | Given → expected | Source |
|---|---|---|
| `test_f4_outside_scaffold_never_touches_user_ci` | `workspace` + own `.pre-commit-config.yaml` and `.github/workflows/ci.yml` → rc 0, both byte-identical, stdout has `#48` | F-4 |
| `test_f4_outside_without_ci_files_succeeds` | bare `workspace` → rc 0, `projects/<name>/pyproject.toml` exists | F-4 |
| `test_f2_outside_source_pins_installed_commit` | `_installed_commit` → `"a"*40` → pyproject line == `datalab = { git = "https://github.com/simonharel-simpro/data-lab", subdirectory = "packages/datalab", rev = "aaaa…" }` | F-2 |
| `test_f2_no_direct_url_uses_main_and_warns` | `_installed_commit` → None → line ends `branch = "main" }`, stderr has the notice | F-2, D-7 |
| `test_u1_inside_decided_by_workspace_not_install` | outside `workspace` while `repo_root` is the real checkout → git source + `<ws>/ruff.toml` + no `wiring.plan` call; `fake_repo` (inside) → path source unchanged, wiring planned, no workspace ruff written | U-1 |
| `test_f10_failed_lock_leaves_no_ruff_toml` | outside, injected `lock` raises `ProjectError` → rc 1, no `<ws>/ruff.toml`, no `.tmp-` dir | F-10 |
| `test_f10_existing_ruff_toml_untouched` | `<ws>/ruff.toml` = `"x = 1\n"` → byte-identical, stdout `kept existing` | F-10, U-7 |
| `test_f5_success_message_names_workspace` | outside success → stdout contains `in workspace <ws>` | F-5 |
| `test_f1_uv_lock_runs_non_interactive` | fake `uv` on PATH dumping env + stdin → `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, stdin empty | F-1 |
| `test_f1_auth_failure_is_classified` | fake `uv` exits 1 with `fatal: could not read Username` → `ProjectError` naming the URL and `gh auth setup-git` | F-1 |
| `test_f3_readme_has_outside_bootstrap` | root `README.md` → contains `uvx --from "git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new` | F-3 |

Existing tests: the scaffold test (`test_scaffold.py`) keeps passing unchanged (inside path); `test_ledger*` keep
reading `REPO_ROOT/contracts` (single source unchanged).

## Exit checks
- `uv run --project packages/datalab pytest` (coverage ≥ 70), `pytest -m scaffold`, pyright strict on src, ruff,
  lint-imports, `pre-commit run --all-files --hook-stage pre-push`.
- Manual (record in IMPLEMENTATION_STATUS): `uv build --wheel` into a tmp dir, install the wheel in a fresh venv, run
  `datalab-new demo` in a tmp workspace with `datalab.toml` using a local `file://` clone as the git source (never the
  GitHub URL in automated tests) → project created, `uv lock` green, `python -m datalab.resources milestones.json`
  prints a site-packages path.
