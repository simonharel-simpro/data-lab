# Phase 3 — Hydra project template, package name, scaffold-and-gate

**Agent:** `python-fastapi` · **Depends on:** Phases 1, 2 · **Plan:** `IMPLEMENTATION_PLAN_EXPERIMENT.md`

**Acceptance:** a freshly generated project is green on its gates — `uv sync --locked`, `lint-imports`, `pyright`,
`pytest --cov` (floor 70 %), `check_declared_dependencies.py`, the Hydra gate (run, not skipped), `ruff check`,
`ruff format --check`, `tools/check_file_size.py` and `pip-audit` — proven by `test_f_3_scaffolded_project_passes_its_gates`;
plus every test below; F-3, F-8 (exit code), F-10…F-13 (Python), F-21, U-3, U-5, U-19, U-25, U-26, U-27 (train/eval),
U-28 (eval), U-29, U-30 handled and tested.

Already exists from Phase 1 (`from datalab import ledger`): `ledger.read(dir)`, `write_atomic`, `new_ledger`, `produce`,
`decide(.., winner=Winner(candidate, run_id))`, `freeze_split`, `record_data`, `test_access_problem(l, split_sha, note)
-> str | None`, `record_test_look(l, split_sha, run_id, note)`, `look_number(l, split_sha)`, `Kind`, `Decision`,
`LedgerError`; `datalab.split` (`Partition`, `Split`, `GroupBound`, `TimeBound`, `read_split`, `split_sha256`,
`SplitError`); `datalab.project.card_metric(dir) -> CardMetric(key, goal)`, `experiment_name`, `load`; `datalab.tags.Tag`
(11 tag names); `datalab.tracking.tracked_trial(run_name, tags=None, *, candidate=None) -> Iterator[Trial]` (refuses a
`project`/`candidate` tag), `tracked_run` (pops the outcome registry, tags `n_children`/`n_failed`/`failed_candidates`),
`preflight`, `TrackingUnavailable`. From Phase 2: `wiring.plan/apply` in `datalab-new`, `fake_repo` copying both config
files, `tools/pre_commit_checks/hydra_gate.py` (`main(argv, *, repo_root)`, prints `hydra-gate <rel>` per gated root).
Existing (a2e1201): `new_project.py:16` `_PLACEHOLDER`, `:30-39` `_rewrite`, `:47` `# noqa: S603  # <reason>`;
`project.py:14` `NAME_RE`; `conftest.py:13-30`; `test_new_project.py:61-67` `test_u_10_no_placeholder_left`, `:122-146`
(real-package copy pattern); purity contract pattern `projects/mini-rag/pyproject.toml:44-52`.

## Files (37)
Template `templates/project/`: new `configs/` (6 YAML), `src/__DATALAB_PACKAGE__/{__init__,paths,candidates,split,
scoring,grid,prepare,train,eval}.py`, `tests/{__init__,conftest,fixture_models,test_units,test_train,test_eval}.py`,
`tests/fixtures/{split.json,sample.jsonl}`, `.gitignore`; modified `pyproject.toml`, `PROJECT.md`, `README.md`; deleted
`src/.gitkeep`. datalab: modified `src/datalab/{project,new_project}.py`, `pyproject.toml`,
`tests/{test_new_project,test_project}.py`; new `tests/test_scaffold.py`. Root: modified `ruff.toml`,
`.github/workflows/ci.yml`, `ARCHITECTURE.md`.

### `templates/project/configs/` (new)
| File | Content |
|------|---------|
| `train.yaml` | `defaults: [{paths: default}, {data: default}, {model: dummy}, {hparams_search: null}, {experiment: default}, _self_]`; `seed: 0`; `hydra: {run: {dir: "${project_dir:}/logs/${now:%Y-%m-%d}/${now:%H-%M-%S}"}, job: {chdir: false}}` |
| `eval.yaml` | `defaults: [{paths: default}, {data: default}, {model: dummy}, _self_]` (a `model` node, so CLI `model.value=0.5` parses at `@hydra.main`); `candidate: null` (→ the ledger winner); `look_note: null`; same `hydra:` block |
| `paths/default.yaml` | `experiment_dir: ${project_dir:}` (holds `split.json` + `run.json`) · `data_file: ${project_dir:}/data/clean/data.jsonl` |
| `data/default.yaml` | `target: y` · `partitions: [train, val]` · `score_on: null` (→ `train` for a comparison ledger, else `val`; U-30) |
| `model/dummy.yaml` | `_target_: __DATALAB_PACKAGE__.candidates.Constant` · `value: 0.0` |
| `experiment/default.yaml` | `name: default` (NAME_RE; `audit` reserved) · `candidates: [dummy]` · `metrics: []` (allowed secondary keys) |
No `hparams_search/` file ships; a grid is `configs/hparams_search/<name>.yaml` = `{<candidate>: {<param>: [v, …]}}`,
picked with `hparams_search=<name>`. No `${oc.env:...}`, no JSON, no `logger/` group (`logger.sub` is dropped).

### `templates/project/src/__DATALAB_PACKAGE__/*.py` (new)
Relative imports inside the package; each module ≤ 200 lines; full type hints.
- `__init__.py` docstring only. `paths.py` — `PROJECT_DIR: Final[Path] = Path(__file__).resolve().parents[2]`;
  `register_resolvers() -> None` registers OmegaConf `project_dir` → `str(PROJECT_DIR)` (`replace=True`), called at
  import of `train`/`eval` (F-10).
- `candidates.py` (pure) — `Row = Mapping[str, object]`; `class Candidate(Protocol): def predict(self, row: Row) -> float`;
  `@dataclass(frozen=True) class Constant: value: float` (`predict` returns it); `config_sha256(model: Mapping[str,
  object]) -> str` = sha256 of `json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` (the one
  helper train tags and eval recomputes).
- `split.py` — `from .candidates import Row` (keeps the import-linter contract: `split` imports `datalab`);
  `SplitAccessError(RuntimeError)`; `read_rows(path) -> list[Row]` (JSON Lines, utf-8-sig, bad line → `ValueError`
  naming the line number); `load_split(experiment_dir: Path, partitions: Collection[Partition], *, rows: Sequence[Row],
  allow_test: bool = False) -> dict[Partition, list[Row]]` — TEST without `allow_test` → `SplitAccessError` (U-3);
  missing `split.json` → `FileNotFoundError` naming it + "freeze the split first (/experiment)"; index lists → `rows[i]`
  (out of range → `SplitError`; the union of the three index lists must equal `range(len(rows))`, else `SplitError`
  "split.json does not cover data_file row for row": index lists address the rows of `data_file`); `GroupBound` → rows whose `str(row[group_key])` is listed; `TimeBound` → previous
  `time_max` < `row[time_col]` ≤ `time_max` (ISO via `datetime.fromisoformat`); only requested partitions materialised.
- `scoring.py` (pure) — `score(predictions, labels) -> float` = −MAE (goal `max`); empty or unequal → `ValueError`;
  `metric_key_problems(child_keys: Mapping[str, frozenset[str]], key: str, allowed: Collection[str], candidates:
  Collection[str]) -> list[str]` — FINISHED children must share one key set ⊆ `{key, "cost_usd", *allowed}`, and no key
  has a token (split on `[._/-]`) equal to a candidate name (token match: `core` never flags `score`).
- `grid.py` (pure) — `Scalar = str | int | float | bool`; `@dataclass(frozen=True) Combo(candidate: str, index: int,
  params: Mapping[str, Scalar])`, `run_name` property `f"{candidate}-{index}"`; `GridError(ValueError)`;
  `expand(candidates: Sequence[str], search: Mapping[str, Mapping[str, Sequence[Scalar]]]) -> list[Combo]` — a search
  key not in `candidates` → `GridError` naming it (U-26); an empty or non-scalar list → `GridError`; per candidate in list
  order, `itertools.product` over sorted param names, index from 0; a candidate without a grid → one `Combo(c, 0, {})`.
- `prepare.py` — `PrepareError(ValueError)` (→ exit 2); `compose_model(config_name: str, overrides: Sequence[str],
  candidate: str) -> DictConfig` — drops every override matching `^[~+]*model=` (the user's group choice never leaks
  into another candidate), `hydra.compose(config_name, [*kept, f"model={candidate}"])` (both train.yaml and eval.yaml
  carry a `model` default, so no `+`), **returns the `model` node**, resolved with `throw_on_missing=True`;
  `hydra.utils.get_object(model._target_)` must import. Every Hydra/OmegaConf error of steps (1)-(6) —
  `MissingMandatoryValue`, `ConfigCompositionException`, `InterpolationResolutionError`, the `ImportError`/
  `AttributeError` of `get_object` — is wrapped `raise PrepareError(...) from err` (exit 2, never a traceback);
  `read_ledger(experiment_dir) -> RunLedger | None` (absent → None; `LedgerError` → `PrepareError`);
  `score_on(cfg, l) -> Partition`; `file_sha256(path) -> str`.
- `train.py` — `register_resolvers()` at import; `@hydra.main(version_base=None, config_path="../../configs",
  config_name="train") main(cfg)`: `HydraConfig.get().mode == RunMode.MULTIRUN` → stderr "--multirun is not supported:
  list candidates and an hparams_search grid instead (D-4)", `SystemExit(2)` (F-12); else `SystemExit(run(cfg,
  tuple(HydraConfig.get().overrides.task)))` when non-zero. `run(cfg: DictConfig, overrides: Sequence[str] = ()) -> int`,
  in order; steps (1)-(6) raise `PrepareError`/`ProjectError`/`SplitError`/`GridError`/`SplitAccessError`/
  `FileNotFoundError` → one stderr line, return 2, no MLflow run (F-11, U-3, U-19):
  (1) `project = load(PROJECT_DIR)`, `metric = card_metric(project.root)`; (2) `experiment_name(project.name,
  cfg.experiment.name)`, `name == "audit"` refused; (3) `OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)`;
  (4) `l = read_ledger(...)`; `on = score_on(cfg, l)` must be in `cfg.data.partitions`; (5) candidates non-empty,
  unique, NAME_RE each; `combos = grid.expand(candidates, cfg.get("hparams_search") or {})`; per combo
  `OmegaConf.merge(compose_model("train", overrides, c), combo.params)` → container + `config_sha256` — **every grid
  param key must already exist in that candidate's model YAML** (the composed node is a struct, so `merge` raises
  `ConfigKeyError` on a new key; wrapped as `PrepareError` naming the candidate and key → exit 2, before any run); (6) rows,
  `load_split(dir, partitions)`, `eval_rows = parts[on]` non-empty; `split_sha = split_sha256(dir/"split.json")`,
  `data_sha = file_sha256(data_file)`; (7) `Settings()` + `preflight` (`TrackingUnavailable` → 1);
  (8) `with tracked_run(project, settings, run_name=name, sub=name, tags={entry: "train", split_sha256, data_sha256,
  score_on})`: params `experiment`, `candidates`, `score_on`, `seed`, `n_combos`; resolved config as `config.yaml`; per
  combo `with tracked_trial(combo.run_name, tags={config_sha256: …}, candidate=combo.candidate)`: `log_params(
  combo.params)`, `instantiate`, `log_metric(metric.key, score(...))`; `MlflowException`/`TrackingUnavailable` are
  **re-raised** (caught at `run` level → stderr `tracking failed: <reason>`, return 1); any other exception is a
  candidate failure: the child is FAILED, logged with its name, the loop continues (this broad catch is the isolation
  boundary, commented as such); (9) FINISHED children's metric keys (`search_runs` on `tags.mlflow.parentRunId`) →
  `metric_key_problems(.., cfg.experiment.metrics, candidates)` non-empty → stderr, return 1; (10) 1 if a child failed
  (F-8) else 0. Never logs `metric.key` or `cost_usd` on the parent.
- `eval.py` — same import-time resolver + MULTIRUN refusal, `config_name="eval"`. `run(cfg, overrides=()) -> int`;
  every refusal before (5) → stderr, return 2, **no MLflow run** (F-21): (1) project + card metric; (2) `l =
  ledger.read(dir)` (missing/invalid → 2: "eval runs at the audit only: /experiment"); (3) `split_sha` of split.json;
  `test_access_problem(l, split_sha, cfg.look_note)` → 2; `file_sha256(data_file) != l.data_sha256` → 2;
  (4) `candidate = cfg.candidate or l.winner.candidate`; `model = compose_model("eval", overrides, candidate)`,
  `h = config_sha256(container)`; (5) `Settings()` + `preflight` (→ 1); winner child `MlflowClient().get_run(
  l.winner.run_id)` and its parent (`mlflow.parentRunId`) (`MlflowException` → 1); the parent's `split_sha256` /
  `data_sha256` tags ≠ `l.split_sha256` / `l.data_sha256` → 2 ("the winner was trained on another split or data");
  the child's `config_sha256` tag ≠ `h` → 2, stderr `config_sha256 differs from the winner's: rerun with model=<winner family>
  model.<k>=<v> …` listing the winner's family and params in that exact CLI form (`python -m <pkg>.eval model=dummy
  model.value=0.5`; without `model=<family>` the `@hydra.main` composition holds `dummy` and refuses any key it lacks); (6) `n = look_number(l, split_sha)`; `with tracked_run(project, settings,
  f"eval-{candidate}", sub="audit", tags={entry: "eval", split: "test", test_look: str(n), split_sha256})` and
  `tracked_trial(f"{candidate}-test", tags={split: "test", test_look: str(n), config_sha256: h}, candidate=candidate)`:
  first `ledger.write_atomic(dir, record_test_look(l, split_sha, trial.run_id, cfg.look_note))`, then `load_split(dir,
  [TEST], rows=rows, allow_test=True)`, logs `test_<metric.key>` only (F-13); return 0 (any exception → child FAILED, 1).
Tag keys always come from `datalab.tags.Tag`. **Reference:** `projects/mini-rag/src/mini_rag/run.py:81-112`;
`~/.claude/skills/trouvetou/CONTRACTS.md:39-69`.

### `templates/project/tests/` (new)
- `fixtures/sample.jsonl`: 7 rows `{"x": i, "y": v}`, y = 0.0 (rows 0-2), 1.0 (3-4), 0.5 (5-6). `fixtures/split.json`:
  `{"strategy": "random", "seed": 0, "target": "y", "group_key": null, "time_col": null, "splits": {"train": [0, 1, 2],
  "val": [3, 4], "test": [5, 6]}}`.
- `conftest.py`: `PROJECT_DIR`, `CONFIGS`, `FIXTURES`; autouse `_isolated` copied from `packages/datalab/tests/
  conftest.py:13-25`; autouse `_resolvers` calling `paths.register_resolvers()` (so a bare `compose` resolves
  `${project_dir:}`); `sqlite_uri` (`:28-30`) + `tracking` fixture (`DATALAB_MLFLOW_TRACKING_URI`); `configs(tmp_path)`
  (copy of `CONFIGS`; tests add model/grid files); `exp_dir(tmp_path)` (fixtures copied to `tmp_path/"exp"`) and
  `data_overrides` = `[f"paths.experiment_dir={exp}", f"paths.data_file={exp}/sample.jsonl"]`; `composed(configs, name,
  overrides)` context manager = `initialize_config_dir(version_base=None, config_dir=str(configs))` + `compose` —
  **every test calls `run(cfg, overrides)` inside it** (so `compose_model` finds the initialised Hydra); `_runs(uri, exp)`;
  `audit_ready(configs, exp_dir, tracking, candidate="dummy")` (factory fixture) — runs train with that candidate, then builds and writes (via `ledger` ops) a
  comparison ledger with metric `"score (max): template"`: scoping, dataset validated → `freeze_split(exp/split.json)` →
  eda validated → `record_data(exp/sample.jsonl)` → modeling validated with `Winner(candidate, <child id>)` → current
  `audit` `todo`; returns `(ledger, child_id)`.
- Subprocess tests use `subprocess.run([sys.executable, "-m", ...], check=False)  # noqa: S603  # fixed argv: this
  interpreter + the package entry + test paths, no shell`.
- `tests/fixture_models.py`: `@dataclass(frozen=True) class Offset: value: float; offset: float` (`predict` → `value +
  offset`), a family with a param `dummy` lacks; written as `configs/model/offset.yaml` (`_target_:
  tests.fixture_models.Offset`, `value: 0.0`, `offset: 0.0`) in the copied configs; subprocess tests that use it pass
  `--config-dir <copied configs>` and `PYTHONPATH=<PROJECT_DIR>` (in-process, pytest's rootdir insertion finds `tests`).
- Extra model files written by tests: `dummy-high` (`Constant`, 1.0), `boom` (`Constant`, value `"nan-text"`), `bad`
  (`_target_: ...candidates.Missing`); grid `configs/hparams_search/g.yaml` = `{dummy: {value: [0.0, 0.5, 1.0]}}`.
  `E = "__DATALAB_PROJECT__/default"`, `A = "__DATALAB_PROJECT__/audit"`.

| File · Test | Given → expected | Source |
|---|---|---|
| `test_units` · `test_score_rejects_empty_or_unequal` | `score([], [])`, `score([1.0], [1.0, 2.0])` → `ValueError`; `score([0.0, 1.0], [1.0, 1.0]) == -0.5` | default |
| `test_units` · `test_read_rows_bad_line_names_it` | line 2 `{"x":` → `ValueError` containing `line 2` | default |
| `test_units` · `test_load_split_index_out_of_range` | train `[0, 9]` on 7 rows → `SplitError` | default |
| `test_units` · `test_load_split_index_split_not_covering_rows_rejected` | 7 rows, split covering 0..5 (row 6 unassigned) → `SplitError`; split covering 0..7 (8 indices) → `SplitError`; the fixture split (0..6) → ok | F-4 |
| `test_units` · `test_load_split_grouped_rows` | grouped `g`, train `["a"]`, val `["b"]`, test `["c"]`; rows a, b, a, c → TRAIN rows 0, 2; VAL row 1; TEST absent | U-3 |
| `test_units` · `test_load_split_temporal_rows` | time_max `2024-01-31`/`02-29`/`03-31`; t `01-15`, `02-10`, `03-01` → train 0, val 1; `allow_test=True` → test 2 | U-3 |
| `test_units` · `test_grid_expand_order` | `expand(["a", "b"], {"a": {"y": [1, 2], "x": [0]}})` → `a-0 {x:0,y:1}`, `a-1 {x:0,y:2}`, `b-0 {}` | U-26 |
| `test_units` · `test_metric_key_problems` | `{"a-0": {score, cost_usd}, "b-0": {score, cost_usd, b_acc}}`, allowed `[]`, candidates `[a, b]` → exactly 3 problems, one per rule broken: sets unequal, `b_acc` not allowed, `b_acc` has token `b`; `core` in candidates, key `score` → `[]` | U-29 |
| `test_train` · `test_u_5_train_logs_one_parent_and_one_child_per_listed_candidate` | candidates `[dummy, dummy-high]` → 0; parent: no `mlflow.parentRunId`, no `score`/`cost_usd`, tags `n_children "2"`, `entry "train"`, `split_sha256` = sha of the fixture split, `score_on "val"`; children `dummy-0` (score −1.0), `dummy-high-0` (0.0), tags `candidate`, 64-hex `config_sha256`, `cost_usd 0.0` | U-5, D-5 |
| `test_train` · `test_u_26_grid_one_child_per_combination` | `hparams_search=g` → 0; children `dummy-0..2`, param `value` `0.0`/`0.5`/`1.0`, scores −1.0/−0.5/0.0, 3 distinct `config_sha256` | U-26 |
| `test_train` · `test_u_26_grid_naming_unknown_candidate_exits_2` | grid `{ghost: {value: [1]}}` → 2, stderr `ghost`, `get_experiment_by_name(E) is None` | U-26 |
| `test_train` · `test_grid_unknown_param_key_exits_2_before_any_run` | grid `{dummy: {offset: [0.1]}}` (`Constant` has no `offset`) → 2, stderr names `dummy` and `offset`; `get_experiment_by_name(E) is None` | U-26 |
| `test_train` · `test_f_8_one_failing_candidate_parent_lists_it_and_exit_nonzero` | `[dummy, boom]` → 1; `boom-0` FAILED, `dummy-0` FINISHED; parent `n_failed "1"`, `failed_candidates "boom-0"` | F-8 |
| `test_train` · `test_tracking_error_is_not_a_candidate_failure` | `mlflow.log_metric` patched to raise `MlflowException("down")` → 1, stderr `tracking failed: down`, only 1 child created | F-8 |
| `test_train` · `test_model_override_dropped_per_candidate` | candidates `[dummy]`, overrides `[*data, "model=dummy-high"]` → 0; `dummy-0` score −1.0 | F-11 |
| `test_train` · `test_f_11_bad_target_fails_before_any_run_created` · `test_f_11_missing_value_fails_before_any_run` | `[dummy, bad]` → 2 · `model.value=???` → 2; both: no experiment `E` | F-11 |
| `test_train` · `test_f_11_composes_without_hparams_search` | no grid → `"hparams_search" not in cfg`, `run == 0` | F-11 |
| `test_train` · `test_u_19_train_refuses_bad_experiment_name` | `experiment.name=Bad_Name` → 2; `experiment.name=audit` → 2; no experiment | U-19 |
| `test_train` · `test_u_3_train_entry_refuses_test_partition` · `test_missing_split_exits_2` | `data.partitions=[train,test]` → 2 · empty `paths.experiment_dir` → 2, stderr `split.json` | U-3, U-24 |
| `test_train` · `test_u_30_comparison_ledger_scores_on_train` | `new_ledger(COMPARISON, "score (max): t")` written in `exp` → 0; parent `score_on "train"`; `dummy-0` score 0.0 | U-30 |
| `test_train` · `test_u_29_secondary_key_not_declared_exits_1` | `Constant.predict` patched to also `mlflow.log_metric("dummy_rate", 1.0)` → 1, stderr `dummy_rate` | U-29 |
| `test_train` · `test_hydra_output_dir_under_project` | `compose("train", return_hydra_config=True)` → `hydra.run.dir` starts with `str(PROJECT_DIR / "logs")`, `hydra.job.chdir is False` | F-10 |
| `test_train` · `test_f_10_train_runs_from_foreign_cwd_without_env` | subprocess `-m <pkg>.train hydra.run.dir={tmp}/h *data`, cwd `tmp/elsewhere`, env only the sqlite URI → 0; 1 parent + 1 child in `E`; `{tmp}/h/.hydra/config.yaml` exists | F-10 |
| `test_train` · `test_f_12_multirun_refused` | subprocess `... --multirun hydra.sweep.dir={tmp}/m` → 2, no experiment | F-12 |
| `test_eval` · `test_f_13_eval_logs_test_prefixed_key_not_metric_key` | `audit_ready` → `run(cfg)` → 0; in `A` child `dummy-test` metrics `{"test_score": -0.5, "cost_usd": 0.0}`, no `score`; parent + child `split "test"`, `test_look "1"`; run.json `test_looks[0].run_id` == child id | F-13, U-28 |
| `test_eval` · `test_f_21_eval_without_ledger_exits_2` | no run.json → 2; `get_experiment_by_name(A) is None` | F-21 |
| `test_eval` · `test_f_21_eval_before_audit_exits_2` | ledger at modeling `produced` → 2, stderr `audit`; no `A` | F-21 |
| `test_eval` · `test_f_21_eval_after_audit_validated_exits_2` | audit produced + validated → 2; no new run | F-21 |
| `test_eval` · `test_u_28_second_look_needs_note` | one look done → `run` → 2 (stderr `note`); `look_note="recheck after fix"` → 0, `test_look "2"`, 2 looks in run.json | U-28 |
| `test_eval` · `test_u_27_config_hash_mismatch_refused` | `model.value=0.5` → 2, stderr contains `model=dummy model.value=`; no `A` | U-27 |
| `test_eval` · `test_eval_refuses_changed_split_or_data` | split.json index moved → 2 (`split.json`); sample.jsonl appended → 2 (`data`) | F-4 |
| `test_eval` · `test_eval_refuses_winner_from_another_split` | `audit_ready`, then `MlflowClient.set_tag(<winner parent>, "split_sha256", "c" * 64)` → `run` returns 2, stderr contains `another split or data`; `get_experiment_by_name(A) is None` (no run created) and run.json `test_looks` unchanged | U-27 |
| `test_eval` · `test_eval_cli_model_override_reaches_hash_check` | subprocess `-m <pkg>.eval model.value=0.5 *data` after `audit_ready`, env only the sqlite URI → exit 2, stderr contains `config_sha256 differs`, not `Could not override` | U-27 |
| `test_eval` · `test_eval_cli_non_dummy_winner_override_form` | `audit_ready(candidate="offset")`; subprocess `-m <pkg>.eval --config-dir <configs> model=offset model.offset=0.5 *data` → exit 2, stderr contains `config_sha256 differs` and `model=offset model.offset=`; the same without `model=offset` → non-zero, stderr `Could not override` (why the hint names the family) | U-27 |

### `templates/project/pyproject.toml` (modify)
`dependencies = ["datalab", "hydra-core==1.3.8", "omegaconf==2.3.1", "mlflow==3.17.2"]` (comment: omegaconf 2.4.0 is the
newest but hydra-core 1.3.8 requires `omegaconf<2.4,>=2.2`; mlflow as datalab's); `"import-linter==2.16"` in `dev`;
`[tool.importlinter]` `root_package = "__DATALAB_PACKAGE__"`, `include_external_packages = true`, `forbidden` contract
`"scoring, candidates, grid stay pure"`: `source_modules = ["__DATALAB_PACKAGE__.scoring", "__DATALAB_PACKAGE__.candidates", "__DATALAB_PACKAGE__.grid"]`
(absolute, pattern `projects/mini-rag/pyproject.toml:51`), `forbidden_modules` `mlflow`, `datalab`,
`hydra`, `omegaconf`; `[tool.pytest.ini_options] testpaths = ["tests"]`; `[tool.coverage.run] source =
["__DATALAB_PACKAGE__"]`; `[tool.coverage.report] show_missing = true` (keep `fail_under = 70`).

### `templates/project/{.gitignore,PROJECT.md,README.md}`
`.gitignore` (new): `logs/`, `outputs/`, `multirun/`, `data/raw/`. `PROJECT.md`: the commented `# metric:` lines →
`metric:` / `  key: score` / `  goal: max`. `README.md`: "Code goes under `src/<your_pkg>/`" → the layout, `uv run python
-m __DATALAB_PACKAGE__.train experiment=default [hparams_search=<grid>]`, `... .eval` (audit only, gated by run.json),
"run the experiment with `/experiment`".

### `packages/datalab/src/datalab/project.py` (modify)
`package_name(name: str) -> str` — `validate_name(name)`, then the rule (verbatim in the overview and `EXPERIMENT.md`):
**`<pkg>` = `name.replace("-", "_")`, refused (exit 2, nothing written) when it is a Python keyword, in
`sys.stdlib_module_names`, or in `set(importlib.metadata.packages_distributions()) | {"hydra", "omegaconf", "antlr4"}`
(the import names of the env `datalab-new` runs in, plus the template's Hydra deps)**; refusal = `ProjectError` (U-25).

### `packages/datalab/src/datalab/new_project.py` (modify)
`main`: `pkg = package_name(args.name)` beside `validate_name` (exit 2, nothing written); `_rewrite(tmp, name, title, pkg)`
also replaces `__DATALAB_PACKAGE__` in contents, then renames every path containing it (deepest first); the leftover
check also scans relative path strings; success message adds the package name and `/experiment`.

### `packages/datalab/pyproject.toml` (modify)
Marker `"scaffold: scaffolds a project with a real uv lock (network); the CI checks job runs it"`; addopts
`-m 'not integration and not scaffold'`.

### datalab tests
| File · Test | Given → expected | Source |
|---|---|---|
| `test_new_project` · `test_u_10_no_placeholder_left` (extend) | `main(["demo-app"])` → no content and no relative path contains `__DATALAB_`; `src/demo_app/train.py` exists | U-10 |
| `test_new_project` · `test_u_25_package_name_refusals_write_nothing` | `class`, `json`, `hydra`, `mlflow` → 2 each; `projects/` empty; both config files byte-identical | U-25 |
| `test_new_project` · `test_importlinter_root_is_the_package` | `main(["demo-app"])` → `tool.importlinter.root_package == "demo_app"` | U-25 |
| `test_project` · `test_package_name_maps_dashes_and_refuses_deps` | `"mini-rag"` → `"mini_rag"`; `"a"` → `"a"`; `"pydantic"`, `"antlr4"`, `"omegaconf"` → `ProjectError` | U-25 |
| `test_scaffold` · `test_f_3_scaffolded_project_passes_its_gates` (`@pytest.mark.scaffold`) | `fake_repo` + real `packages/datalab` copy (pattern `test_new_project.py:122-146`) + real `tools/` and `contracts/` (the ledger reads `contracts/milestones.json` via `repo_root()`); `main(["ci-scaffold"], root=fake_repo)` with the real `_uv_lock` → 0; in the project `uv sync --locked`, `lint-imports`, `pyright`, `pytest -q --cov`, `pip-audit`, `check_declared_dependencies.py`, `ruff check .`, `ruff format --check .` all exit 0; from the `fake_repo` root (cwd), `[sys.executable, "tools/check_file_size.py", *<projects/ci-scaffold/src/ci_scaffold/*.py, globbed in Python, relative>]` (relative paths: the script's `_in_scope` needs `projects/<n>/src/…`) exits 0; `hydra_gate.main(["projects/ci-scaffold"], repo_root=fake_repo)` → 0 and `capfd` stdout contains `hydra-gate projects/ci-scaffold` (gate ran, not `skip`) | F-3 |

### `ruff.toml`, `.github/workflows/ci.yml`, `ARCHITECTURE.md` (modify)
`ruff.toml`: `[lint.isort]` `known-first-party = ["__DATALAB_PACKAGE__"]`. `ci.yml` job `checks`, after the datalab
step: `- name: scaffold a fresh project and run its gates (F-3; network for uv lock)`, `working-directory:
packages/datalab`, `run: uv run --locked pytest -m scaffold -q`. ARCHITECTURE: Project Structure (`:37`) the template tree;
Layer Responsibilities (`:65`) a *Project template* entry (train/eval own I/O; scoring/candidates/grid pure; the
`train.run` step order); Data Flow (`:221`) train → parent/children → eval gate → test look.

<!-- plan-validate: READY 2026-11-06 sha256:0d2ac3cdc9be -->
