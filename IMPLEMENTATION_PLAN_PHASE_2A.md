# Phase 2A — Shared `datalab` package, project template, `datalab-new`, CI

**Depends on:** Phase 1 (`compose.yaml`, `ruff.toml`, `contracts/name_vectors.json`, `projects/.gitkeep`).
**Runs in parallel with:** 2B, 2C. **Agent:** `general-purpose` (Python 3.12, uv, pydantic-settings, weaviate-client v4, mlflow).
**Repo root:** `/home/simon/projects/data-science/data-lab`.

## Context
Every project lives in `projects/<name>/` with its **own** uv env and depends on this package by path. The package
gives: project identity (from `PROJECT.md`), naming (Weaviate collections, MLflow experiments), settings + Weaviate
connection, MLflow preflight + a tracked run that always carries the tag `project=<name>`.
Shared infra ports: MLflow 127.0.0.1:5050, Weaviate 127.0.0.1:8090 (HTTP) / 50052 (gRPC).
Reference implementation to reuse: `/home/simon/projects/data-science/Demo-RAG-crag-dataset/src/crag_rag/`
(`config.py:11-56`, `index.py:47-64` and `:178-189`, `tracking.py:43-81`).

## Files

#### `packages/datalab/pyproject.toml` (NEW)
hatchling; package `src/datalab`; deps `pydantic-settings`, `pyyaml`, `weaviate-client` (v4, same version as the
Demo-RAG `uv.lock`), **`mlflow==3.17.2`** (full package, same version as the server image; it brings the
sqlite store used by tests), `httpx`; dev group `pytest`, `pytest-cov`, `pyright`; `[project.scripts] datalab-new = "datalab.new_project:main"`; pytest marker `integration`;
`addopts = "-ra --strict-markers -m 'not integration'"`; coverage `fail_under = 70`. Ruff config comes from the root
`ruff.toml` (no `[tool.ruff]` here). Pin via `uv.lock`.

#### `packages/datalab/src/datalab/project.py` (NEW) — pure: no weaviate/mlflow import
- `NAME_RE: Final = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")` — comment: "identical literal in
  app/src/lib/name.ts; vectors in contracts/name_vectors.json".
- `RESERVED: Final = frozenset({"test", "datalab", "datalab-test", "template", "y", "n", "yes", "no", "on", "off", "true", "false", "null"})`.
- `class ProjectError(ValueError)` — message always names the file and the problem.
- `@dataclass(frozen=True) class Project: name: str; root: Path`.
- `validate_name(name: object) -> str` — must be `str`, match NAME_RE, not in RESERVED, else `ProjectError` (U-2, U-4, F-3).
- `repo_root(start: Path | None = None) -> Path` — walk up from `start or Path(__file__)` to the first dir containing both `packages/datalab` and
  `compose.yaml`; no subprocess; `ProjectError("repo root not found …")` otherwise (F-10). **Constraint:** this
  only works for editable installs (the template's path dep and `uv tool install --editable` both are); a
  non-editable install must fail with that `ProjectError`, never resolve to site-packages.
- `load(start: Path | None = None, *, root: Path | None = None) -> Project` — `root = root or repo_root()`; walk up
  from `start or Path.cwd()` to the first `PROJECT.md`, stopping at `root` **or the filesystem root, whichever comes
  first**; a card found outside `root / "projects"` (or none found) → `ProjectError`; read `utf-8-sig`, normalise `\r\n`; frontmatter = text between a leading `---` line
  and the next `---` line (CRLF-tolerant regex); `yaml.safe_load` must give a `dict`; `name` validated; `name` must
  equal the containing folder name (S-9). Python does NOT validate status/metric/sections (single source in the app, D-3).
- `collection_name(project: str, *parts: str) -> str` — readable `<Pascal(project)>_<parts joined by _>` sanitised
  with Demo-RAG's `_UNSAFE` regex, + `_` + `sha256(json.dumps([project, *parts]))[:8]`; every part must be `str`
  (`TypeError` otherwise) (U-2, U-3). Pascal: split on `-`, capitalize each.
- `experiment_name(project: str, sub: str | None = None) -> str` — `project` or `f"{project}/{sub}"`; `sub`
  validated with NAME_RE (U-7, F-6).

#### `packages/datalab/src/datalab/settings.py` (NEW)
`class Settings(BaseSettings)`: `model_config = SettingsConfigDict(env_prefix="DATALAB_", env_file=".env",
env_ignore_empty=True, extra="ignore")` (F-5); fields `weaviate_host="127.0.0.1"`, `weaviate_http_port=8090`,
`weaviate_grpc_port=50052`, `mlflow_tracking_uri="http://127.0.0.1:5050"`. `@contextmanager
connect_weaviate(settings) -> Iterator[weaviate.WeaviateClient]` — copy of Demo-RAG `index.py:178-189`
(`connect_to_local` with both ports + timeouts), always closes.

#### `packages/datalab/src/datalab/tracking.py` (NEW)
- `class TrackingUnavailable(RuntimeError)`.
- `preflight(uri: str) -> None` — Demo-RAG `tracking.py:43-55`: `mlflow.set_tracking_uri(uri)` explicitly, GET
  `/health` (5 s), `search_experiments(max_results=1)`; log the resolved URI at INFO.
- `@contextmanager tracked_run(project: Project, settings: Settings, run_name: str, sub: str | None = None, tags:
  Mapping[str, str] | None = None) -> Iterator[str]` — first `mlflow.set_tracking_uri(settings.mlflow_tracking_uri)`
  (so a project that skips `preflight` still never logs through an inherited `MLFLOW_TRACKING_URI`, F-5), then
  `set_experiment(experiment_name(project.name, sub))`, `start_run`, set tags
  `{"project": project.name} | tags`; a caller tag `project` raises `ValueError` (Demo-RAG `tracking.py:73-75`);
  exception inside → run FAILED (mlflow default), re-raised.

#### `packages/datalab/src/datalab/new_project.py` (NEW) — `datalab-new <name> [--title T]`
`def main(argv: list[str] | None = None, *, root: Path | None = None) -> int` (console script calls `main()` and
`sys.exit`s its code; tests pass `argv` and a fake `root`). argparse; `validate_name`; `root = root or repo_root()`;
template `root/"templates"/"project"`; target `root/"projects"/name` — refuse if it exists in any form (dir, empty dir,
file): exit 2, nothing written (U-10). Copy `templates/project` into a dot-temp sibling
`projects/.<name>.tmp-<random>` with `shutil.copytree(ignore=ignore_patterns(".venv", "__pycache__", ".pytest_cache",
".ruff_cache", ".env", "uv.lock"))` (F-9); replace token `__DATALAB_PROJECT__` → name and `__DATALAB_TITLE__` →
title (default: the name) in text files only (decode utf-8, skip undecodable). In `PROJECT.md` the title is
written as a **YAML-escaped double-quoted scalar** (`json.dumps(title, ensure_ascii=False)` is valid YAML) so
`RAG: v2 # b` survives (G-7); the template line is `title: __DATALAB_TITLE__` and the replacement inserts the quoted
form. Assert no file still contains a token;
`os.rename` temp → target; on any error remove the temp dir and exit 1 with the reason (F-8). Print next steps
(`cd projects/<name> && uv sync`). ≤ 80 lines.

#### `templates/project/` (NEW) — becomes a valid uv project **only after token substitution** (uv rejects the raw
name `proj-__DATALAB_PROJECT__`): never `uv sync` the template itself; outside the `projects/*/PROJECT.md` glob
- `PROJECT.md`: frontmatter `name: __DATALAB_PROJECT__`, `title: __DATALAB_TITLE__`, `status: idée`, `tags: []`;
  sections `## Objectif`, `## Approche`, `## Enseignements`, `## Suite`, each holding only an HTML comment with
  guidance (comments count as empty, U-9c). Commented hints for `data:` and `metric: {key, goal}`.
- `pyproject.toml`: name `proj-__DATALAB_PROJECT__` (prefixed so a project called e.g. `mlflow` never shadows a
  dependency in `uv sync`, G-12), Python ≥ 3.12, **`[build-system]` hatchling** with
  `[tool.hatch.build.targets.wheel] only-include = ["src"]` and `sources = ["src"]` — without a build system uv treats
  the project as virtual and `src/<pkg>` is not importable (`ModuleNotFoundError`, reproduced by validation). **Also
  `[tool.hatch.build] dev-mode-dirs = ["src"]`**: without it, the first `uv sync` on a project whose `src/` holds only
  `.gitkeep` writes no editable `.pth`, so a package added afterwards stays unimportable until
  `uv sync --reinstall-package` (reproduced by validation; `dev-mode-dirs` fixes it). Dep `datalab` with
  `[tool.uv.sources] datalab = { path = "../../packages/datalab", editable = true }`, dev `pytest`.
- `.env.example`: copy of the root one. `README.md`: 10 lines (`uv sync`, use `datalab.project.load()`,
  `tracked_run`, `collection_name`). `src/__DATALAB_PROJECT_PKG__/__init__.py` is NOT needed: keep the template
  flat (`src/` empty with `.gitkeep`) to avoid a package-name token.

#### `.github/workflows/ci.yml` (NEW, or append if 2B created it first) — CI-parity
Job `checks` (ubuntu, Python 3.12, uv): `uvx pre-commit run --all-files`; `uvx pytest tests/` (Phase 1's compose
test; Docker is available on ubuntu runners); `cd packages/datalab && uv sync &&
uv run pytest --cov=datalab` (unit only; integration excluded by marker). Checkout with `submodules: false`
(fork not needed for Python). 2B appends an `app` job; 3 appends a `pilot` job.

#### Mechanical rule — declared dependencies (from the overview's Mechanical Rules table)
Run `/scaffold-linter declared-deps --recipe python-fastapi-layered/check_declared_dependencies.py` scoped to
`packages/datalab` once its imports exist, and wire it into `.pre-commit-config.yaml` (and therefore CI).

#### `README.md` (MODIFY) — fill the "New project" section: `uv tool install --editable packages/datalab` (or
`uv run --project packages/datalab datalab-new <name>`), naming rules, what the template contains.

#### `ARCHITECTURE.md` (MODIFY) — add a short real extract of `tracked_run` and `collection_name` under
"Layer responsibilities → shared package".

## Tests — `packages/datalab/tests/`
`conftest.py`: autouse fixture deleting every `DATALAB_*` and `MLFLOW_*` env var and chdir into `tmp_path`; build
`Settings(_env_file=None)` in tests (F-15). Fixture `sqlite_uri(tmp_path) -> f"sqlite:///{tmp_path / 'mlflow.db'}"`
for every MLflow test (pattern: `Demo-RAG-crag-dataset/tests/test_pipeline_usage.py:22`); tests pass it via
`Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)` — never a file store, never the live server.
Fixture `fake_repo(tmp_path)`: a tree with `compose.yaml`, `packages/datalab/` (empty dir), `projects/` and a minimal
`templates/project/` (PROJECT.md + pyproject.toml with the tokens, plus `.venv/`, `.env`, `uv.lock` decoys); tests of
`load()` and `new_project.main()` pass `root=fake_repo` and never touch the real repo.

| Test | Given → expected | Source |
|---|---|---|
| `test_project.py::test_f_12_name_re_matches_shared_vectors` | every `accept` in `contracts/name_vectors.json` → `validate_name` returns it; every `reject` → `ProjectError` | F-12, U-2, U-4 |
| `test_u_2_collection_name_differs_for_names_with_same_pascal` | `collection_name("a-bc","x")` ≠ `collection_name("ab-c","x")` | U-2 |
| `test_u_3_hash_distinguishes_part_boundaries` | `("p","a_b","c")` vs `("p","a","b_c")` → different names | U-3 |
| `test_u_3_readable_part_is_weaviate_safe` | `("mini-rag","bge/v1.5")` → matches `^[A-Z][A-Za-z0-9_]*$`, starts `MiniRag_` | U-3 |
| `test_u_3_non_str_part_raises_type_error` | `collection_name("p", 3)` → `TypeError` | U-3 |
| `test_u_7_experiment_name_format` | `("p")` → `"p"`; `("p","bm25")` → `"p/bm25"`; `("p","Bad")` → `ProjectError` | U-7, F-6 |
| `test_f_11_crlf_and_bom_frontmatter_parse` | BOM + CRLF card with `name: demo` in folder `demo` → `Project(name="demo")` | F-11 |
| `test_f_11_empty_or_list_frontmatter_raises_project_error` | `---\n---` and `---\n- a\n---` → `ProjectError` naming the file | F-11 |
| `test_f_11_yaml_bool_name_rejected` | `name: no` → `ProjectError` | F-11 |
| `test_f_11_walk_up_stops_at_repo_root` | `load(start=fake_repo/"projects"/"x", root=fake_repo)` with no card there and a stray `PROJECT.md` in `tmp_path` (above `fake_repo`) → `ProjectError` | F-11 |
| `test_load_outside_root_raises` | `load(start=tmp_path/"elsewhere", root=fake_repo)` → `ProjectError` (walk ends at the filesystem root) | F-11 |
| `test_s9_name_must_equal_folder` | folder `alpha`, `name: beta` → `ProjectError` | S-9 |
| `test_f_10_root_found_from_nested_git_repo_cwd` | cwd inside a nested dir with its own `.git` → `repo_root()` is data-lab's root | F-10 |
| `test_f_10_non_editable_install_raises` | `repo_root(start=tmp_path/"site-packages"/"datalab"/"project.py")` (give `repo_root` an optional `start: Path` defaulting to `Path(__file__)`) in a tree without `packages/datalab` + `compose.yaml` → `ProjectError` | F-10 |
| `test_b1_package_added_after_first_sync_imports` (`@pytest.mark.integration`: needs `uv` + network-free cache) | `datalab-new demo` in `fake_repo` (with the real template copied in), `uv sync`, then create `src/demo_pkg/__init__.py` → `uv run python -c "import demo_pkg"` exits 0 | B-1 (validation 2) |
| `test_f_5_tracked_run_uses_settings_uri_not_env` | env `MLFLOW_TRACKING_URI=http://127.0.0.1:9`, `Settings(mlflow_tracking_uri=sqlite_uri)`, no preflight → run is found in the sqlite store | F-5 |
| `test_f_5_settings_ignores_bare_mlflow_tracking_uri` | env `MLFLOW_TRACKING_URI=http://localhost:5000` → `Settings().mlflow_tracking_uri == "http://127.0.0.1:5050"`; `DATALAB_MLFLOW_TRACKING_URI=x` → `x` | F-5 |
| `test_tracking.py::test_project_tag_cannot_be_overridden` | `sqlite_uri`; `tracked_run(project, settings, "r", tags={"project":"x"})` → `ValueError` | contract |
| `test_tracked_run_sets_project_tag_and_experiment` | `sqlite_uri` → run in experiment `p/bm25` with tag `project=p`, status FINISHED | contract |
| `test_tracked_run_exception_marks_failed` | `sqlite_uri`; body raises `RuntimeError` → re-raised, run status FAILED | contract |
| `test_preflight_unreachable_raises_tracking_unavailable` | `preflight("http://127.0.0.1:9")` → `TrackingUnavailable` | resilience |
| `test_settings.py::test_g_10_ports_agree_everywhere` | `Settings(_env_file=None)` defaults == values parsed from root `.env.example` == host ports in `docker compose config --format json` (8090, 50052, 5050) (skip the compose part if docker is absent) | G-10, F-4 |
| `test_new_project.py::test_g_7_title_with_yaml_specials` | `datalab-new demo --title "RAG: v2 # b"` → `yaml.safe_load` of the frontmatter gives `title == "RAG: v2 # b"` | G-7 |
| `test_g_12_package_name_prefixed` | generated `pyproject.toml` has `name = "proj-demo"` | G-12 |
| `test_new_project.py::test_u_10_new_project_excludes_venv_and_lock` (= `test_f_9_…`) | template with `.venv/`, `.env`, `uv.lock` → none in output | U-10, F-9 |
| `test_u_10_no_placeholder_left` | output contains no `__DATALAB_` token; `PROJECT.md` loads via `project.load()` | U-10 |
| `test_u_10_refuses_existing_empty_dir_and_writes_nothing` | existing empty `projects/x` → exit 2, tree unchanged | U-10 |
| `test_f_8_failed_copy_leaves_no_project_dir` | rewrite monkeypatched to raise → no `projects/x`, no `.x.tmp-*`; re-run succeeds | F-8 |
| `test_f_3_reserved_names_rejected` | `datalab-new test` → exit 2 | F-3 |
| `test_integration.py::test_f_4_rest_insert_visible_via_grpc_query` (`@pytest.mark.integration`) | token `sub = "t" + uuid4().hex[:8]` (always starts with a letter, so NAME_RE accepts it, G-4); collection `collection_name("datalab-test", sub)` — `datalab-test` is **reserved**, so no real project can own it; insert via REST, bm25 query via gRPC → 1 hit; cleanup in `finally`. MLflow side: `tracked_run(Project(name="datalab-test", root=tmp_path), Settings(), "it", sub=sub)` — `Project` is built directly (the dataclass does not validate; only `load()`/`validate_name` do), experiment `datalab-test/<sub>`, deleted by exact name after | F-4, G-4 |
| `test_f_3_cleanup_deletes_only_created_names` | fake client records deletes → only the exact created collection/experiment names, never a prefix | F-3, S-11 |

Integration tests skip (not error) when services are down (probe `/v1/.well-known/ready` and MLflow `/health`).

## Done when
`uv run pytest --cov` ≥ 70 %, pyright clean (basic), ruff clean, `pytest -m integration` green with
`docker compose up -d`, `datalab-new demo` creates a project that `uv sync`s, CI workflow green on push.

<!-- plan-validate: READY 2026-11-03 sha256:14000bd54791 -->
