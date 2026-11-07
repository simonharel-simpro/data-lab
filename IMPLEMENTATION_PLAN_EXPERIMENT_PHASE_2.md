# Phase 2 — Hydra gate, ledger hook, `datalab-new` wiring, CI matrix

**Agent:** `python-fastapi` · **Depends on:** Phase 1 · **Plan:** `IMPLEMENTATION_PLAN_EXPERIMENT.md`

**Acceptance:** every test below passes under `gates-datalab`; `pre-commit run --all-files` and CI are green on the
current tree (mini-rag and voice-arch have no `configs/`, so the Hydra gate skips them and the ledger hook finds no
run.json); F-1, F-2, F-17, U-8, U-21, U-22 handled and tested; the existing `voice-arch` stanzas are reproduced byte for
byte by `wiring.py` (dual-site guard).

Already exists from Phase 1: `python -m datalab.ledger validate PATH...` (maps `run.json`/`split.json` to their dir,
exit 0/1/2, needs only the datalab env), `contracts/EXPERIMENT.md`.
Existing code (a2e1201): `new_project.py:47` (the `# noqa: S603  # <reason>` pattern), `:56-83` `main` (exit 2 usage,
1 failure, tmp + `os.rename` `:72-77`); tests `conftest.py:33-46` `fake_repo`; hook stanzas `.pre-commit-config.yaml:34-46`
(declared-deps-*, voice-arch `:41-46`), `:56-69` (gates-*, voice-arch `:63-69`), `gates-datalab` `:49-55`; CI jobs
`pilot` `.github/workflows/ci.yml:74-94`, `voice-arch` `:96-116`; `ruff.toml:1-12`.

## Files (11)
New: `tools/check_hydra_project.py`, `tools/pre_commit_checks/hydra_gate.py`, `packages/datalab/src/datalab/wiring.py`,
`packages/datalab/tests/{test_wiring,test_hydra_gate}.py`. Modified: `packages/datalab/src/datalab/new_project.py`,
`packages/datalab/tests/conftest.py`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `ruff.toml`, `ARCHITECTURE.md`.

### `tools/check_hydra_project.py` (new, vendored)
Copy `~/.claude/skills/trouvetou/assets/check_hydra_project.py` (136 lines) byte for byte; insert after line 1 (shebang):
`# >>> vendored header` / `# Vendored verbatim from trouvetou assets/check_hydra_project.py on 2026-11-06,` /
`# sha256 312f6242dc31e4d7930a13d33df9cbed3537aa2ff3fc444f0c9dcf67252a61b2. Do not edit: re-vendor, update the hash.` /
`# <<< vendored header`. It passes `ruff check`; `ruff format` would rewrite it, hence the `ruff.toml` exclude.

### `tools/pre_commit_checks/hydra_gate.py` (new)
`pass_filenames`-tolerant entry: changed paths → project roots → the vendored gate once per root, plus the
`${oc.env:` check. Stdlib only (pre-commit `language: python`).
- `REPO_ROOT: Final = Path(__file__).resolve().parents[2]`; `GATE: Final = REPO_ROOT / "tools" / "check_hydra_project.py"`.
- `project_roots(paths: Sequence[str], repo_root: Path) -> list[Path]` — relative paths resolved against `repo_root`;
  keep those under `repo_root/"projects"/<n>` (the dir itself counts); sorted, unique; empty → every `projects/*` dir
  not starting with `.`.
- `env_interpolations(project: Path) -> list[str]` — `"<rel>:<line>"` per line of `configs/**/*.y*ml` matching
  `\$\{\s*oc\.env\s*:`.
- `main(argv: list[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int` — per root: no `configs/` → stdout
  `skip <rel>: no configs/`; else stdout `hydra-gate <rel>`, then `subprocess.run([sys.executable, str(GATE),
  str(root)], check=False)  # noqa: S603  # fixed argv: this interpreter + the vendored gate + a repo path, no shell`
  and the env check (each hit on stderr); exit 1 if any root failed, else 0. `if __name__ == "__main__"` → `sys.exit(main())`.

### `packages/datalab/src/datalab/wiring.py` (new)
Text-level, idempotent wiring of one project into `.pre-commit-config.yaml` and `ci.yml` (a PyYAML dump would drop the
comments), plus the parity check. Regions: `# >>> datalab-new: <label>` / `# <<< datalab-new: <label>` (labels
`declared-deps`, `gates` in pre-commit at indent 6; `matrix` in ci.yml at indent 10).
- `declared_deps_block(name: str) -> str` and `gates_block(name: str) -> str` — exactly the voice-arch stanzas
  (`.pre-commit-config.yaml:41-46`, `:63-69`) with `voice-arch` → `name`, each ending in `"\n"`.
- `@dataclass(frozen=True) class WiringPlan: writes: tuple[tuple[Path, str], ...]` (only files whose text changes).
- `plan(root: Path, name: str) -> WiringPlan` — each region exactly once (else `ProjectError`); pre-commit regions split
  into blocks at `^      - id: (\S+)$` (comment lines inside a block stay with it), a block added when its id is absent,
  blocks re-emitted sorted by id, text verbatim; matrix region lines `^          - (\S+)$` as a sorted set; the new text
  must `yaml.safe_load` and contain the new ids, else `ProjectError`.
- `apply(plan: WiringPlan) -> None` — per file: tmp in the same dir, write, `os.replace`.
- `parity_problems(root: Path) -> list[str]` — projects = dirs `root/"projects"/*` with a `pyproject.toml`, not starting
  with `.`; hook ids from every `repos[*].hooks[*].id`; ci.yml via `yaml.safe_load` (its `on:` key loads as `True`:
  never index `"on"`); problems: missing `declared-deps-<n>`/`gates-<n>`; `<n>` absent from
  `jobs.projects.strategy.matrix.project`; a matrix entry without a project dir; `fail-fast` not `False`; no step in
  `jobs.projects.steps` whose `run` contains `tools/pre_commit_checks/hydra_gate.py projects/${{ matrix.project }}`;
  no step whose `run` contains `python -m datalab.ledger validate projects/${{ matrix.project }}`.
**Reference:** `new_project.py:72-77`.

### `packages/datalab/src/datalab/new_project.py` (modify)
After `lock(tmp)` and BEFORE `os.rename`: `wiring_plan = wiring.plan(root, name)` (a `ProjectError` → existing except
branch: exit 1, tmp removed, nothing written anywhere); after the rename: `wiring.apply(wiring_plan)`; an `OSError` there
→ stderr `created <target>, but hook/CI wiring failed: <err>; the parity test fails until it is fixed`, exit 1.

### `.pre-commit-config.yaml` (modify)
Bracket the `declared-deps-mini-rag`/`-voice-arch` stanzas (`:34-46`) with `      # >>> datalab-new: declared-deps` /
`      # <<< datalab-new: declared-deps`, and `gates-mini-rag`/`-voice-arch` (`:56-69`) with the `gates` pair. After the
declared-deps region add:
```yaml
      - id: hydra-gate
        name: Hydra is wired in projects with configs/
        entry: python tools/pre_commit_checks/hydra_gate.py
        language: python
        files: ^projects/[^/]+/(configs/|src/|pyproject\.toml)
      - id: ledger
        name: run.json / split.json are valid experiment ledgers
        # --project keeps the repo-root cwd, so pre-commit's relative file names resolve (--directory would not).
        entry: uv run --locked --project packages/datalab python -m datalab.ledger validate
        language: system
        files: ^projects/[^/]+/(run|split)\.json$
```
`gates-datalab` `files` (`:55`) becomes
`^(packages/datalab/|contracts/|tools/|projects/[^/]+/pyproject\.toml$|\.pre-commit-config\.yaml$|\.github/workflows/ci\.yml$|app/src/lib/card\.ts$)`.

### `.github/workflows/ci.yml` (modify)
Replace jobs `pilot` (`:74-94`) and `voice-arch` (`:96-116`) with exactly (2-space job indent; matrix items at 10 spaces,
the indentation `wiring.py` parses):
```yaml
  projects:
    name: project (${{ matrix.project }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        project:
          # >>> datalab-new: matrix
          - mini-rag
          - voice-arch
          # <<< datalab-new: matrix
    defaults:
      run:
        working-directory: projects/${{ matrix.project }}
    # Unit tests only: no Weaviate, LiveKit, MLflow server or LLM endpoint in CI; integration tests are deselected.
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@v6
      - name: gates (contracts, types, deps) + unit tests + coverage floor
        run: |
          uv sync --locked
          uv run --locked lint-imports
          uv run --locked pyright
          uv run --locked pip-audit
          uv run --locked pytest --cov
      - name: Hydra gate (skips a project without configs/)
        working-directory: .
        run: python tools/pre_commit_checks/hydra_gate.py projects/${{ matrix.project }}
      - name: experiment ledger (run.json / split.json; ok when neither exists)
        working-directory: .
        run: uv run --locked --project packages/datalab python -m datalab.ledger validate projects/${{ matrix.project }}
```

### `ruff.toml` (modify)
Add `[format]` `exclude = ["tools/check_hydra_project.py"]` (vendored verbatim; the hooks pass `--force-exclude`).

### `packages/datalab/tests/conftest.py` (modify)
`fake_repo` also copies `REPO_ROOT/.pre-commit-config.yaml` and `REPO_ROOT/.github/workflows/ci.yml` (same relative
paths); new fixture `wired_repo(fake_repo) -> Path` adds stub `projects/{mini-rag,voice-arch}/pyproject.toml`, so parity
starts clean.

### `packages/datalab/tests/test_wiring.py` (new)
| Test | Given → expected | Source |
|---|---|---|
| `test_u_8_new_project_passes_parity_test` | `wired_repo`: `parity_problems == []`; `main(["demo"], root=wired_repo, lock=_no_lock)` → 0; problems `[]`; ids `declared-deps-demo`, `gates-demo` present; matrix `["demo", "mini-rag", "voice-arch"]` | U-8 |
| `test_blocks_reproduce_voice_arch_stanzas_byte_for_byte` | real `REPO_ROOT/.pre-commit-config.yaml`: the text of the `declared-deps-voice-arch` block (from `- id:` to the next `- id:`/region end) `== declared_deps_block("voice-arch")`; same for `gates_block("voice-arch")` | dual-site |
| `test_wiring_is_idempotent` | `apply(plan(root, "demo"))` twice → second plan has no writes; bytes identical | U-8 |
| `test_wiring_keeps_comments` | after `apply`, `# CI: this hook scans staged files only; ci.yml runs a full-history scan` still present | U-8 |
| `test_missing_marker_writes_nothing` | `# >>> datalab-new: gates` removed → `main(["demo"])` == 1, no `projects/demo`, both files byte-identical | U-8 |
| `test_wiring_failure_after_publish_is_reported` | `wiring.apply` patched to raise `OSError("disk")` → exit 1, `projects/demo` exists, stderr contains `hook/CI wiring failed: disk` | U-8 |
| `test_parity_reports_unwired_project` | `wired_repo` + `projects/ghost/pyproject.toml` → problems name `declared-deps-ghost`, `gates-ghost`, matrix `ghost` | U-8 |
| `test_parity_reports_missing_gate_steps` | ci.yml copy without the ledger step → a problem mentions `datalab.ledger validate`; without the Hydra step → mentions `hydra_gate.py` | F-17 |
| `test_f_17_ci_matrix_fail_fast_false_and_covers_every_project` | real `REPO_ROOT` → `parity_problems == []`; `jobs.projects.strategy["fail-fast"] is False` | F-17 |
| `test_f_1_ledger_hook_given_file_paths_validates_their_project` | hook `ledger` entry == `uv run --locked --project packages/datalab python -m datalab.ledger validate`; its `files` regex matches `projects/x/run.json`, `projects/x/split.json`, not `projects/x/run.2026-11-06.json`; `ledger.main(["validate", "projects/demo/run.json"])` with cwd = a tmp repo holding a valid card + ledger + artifacts → 0, an invalid ledger → 1 | F-1 |

`_no_lock` is imported from `tests.test_new_project` (`:18`, the no-op `lock=` passed to `main`).

### `packages/datalab/tests/test_hydra_gate.py` (new)
Loads the wrapper with `importlib.util.spec_from_file_location` from `REPO_ROOT / "tools" / "pre_commit_checks" /
"hydra_gate.py"`, passes `repo_root=tmp_path`, and reads output with **`capfd`** (the vendored gate prints from a
subprocess, which `capsys` does not see). A *wired* demo = `projects/demo/{pyproject.toml (hydra-core dep),
configs/train.yaml (defaults:), configs/model/a.yaml (_target_:), src/demo/train.py (import hydra, @hydra.main(,
instantiate()}`.

| Test | Given → expected | Source |
|---|---|---|
| `test_f_1_hook_entry_with_two_changed_configs_in_one_project_exits_0` | wired demo; argv = two config paths of `demo` → 0; stdout contains `hydra-gate projects/demo` exactly once | F-1 |
| `test_f_2_hydra_hook_files_regex_matches_src_and_pyproject` | `hydra-gate` `files` regex (from the real config) matches `projects/d/src/d/train.py`, `projects/d/pyproject.toml`, `projects/d/configs/train.yaml`; not `projects/d/README.md`, not `packages/datalab/src/x.py` | F-2, U-21 |
| `test_u_22_gate_fails_project_with_configs_but_no_hydra_main` | wired demo without `@hydra.main(` → 1 | U-22 |
| `test_project_without_configs_skipped` | `projects/legacy/src/legacy/x.py` → 0, stdout `skip projects/legacy: no configs/` | S-3 |
| `test_oc_env_in_configs_fails` | wired demo + `configs/paths/default.yaml` line 2 `token: ${oc.env:SECRET}` → 1, stderr contains `configs/paths/default.yaml:2` | default |
| `test_no_args_scans_every_project` | no argv; wired demo + an unwired project with `configs/` → 1 | F-1 |
| `test_vendored_gate_body_matches_trouvetou_sha256` | `tools/check_hydra_project.py` minus the header block → sha256 `312f6242dc31e4d7930a13d33df9cbed3537aa2ff3fc444f0c9dcf67252a61b2` | S-10 |

### `ARCHITECTURE.md` (modify)
Project Structure (`:37`): `tools/check_hydra_project.py`, `tools/pre_commit_checks/hydra_gate.py`, `datalab/wiring.py`;
the CI line (`:58-60`) → job `projects` (matrix); Data Flow (`:221`): `datalab-new` → wiring → hooks + CI matrix.
Branch protection: the required checks `pilot` and `voice-arch` become `project (mini-rag)` / `project (voice-arch)`;
the user renames them after this phase merges.

<!-- plan-validate: READY 2026-11-06 sha256:51dda972e572 -->
