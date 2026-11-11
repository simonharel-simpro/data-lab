# Phase 1 — Experiment contract + datalab ledger, split and trial helpers

**Agent:** `python-fastapi` · **Depends on:** nothing (base `main` @ a2e1201) · **Plan:** `IMPLEMENTATION_PLAN_EXPERIMENT.md`

**Acceptance:** every test below passes under `gates-datalab` (lint-imports, pyright, `pytest --cov=datalab`, floor 70 %
`packages/datalab/pyproject.toml:59`); new `src/` modules ≤ 200 lines; F-4…F-9 (F-8 helper), F-14…F-16, F-18 (Python),
F-21 (helper), U-1, U-2, U-10, U-14, U-15, U-16, U-18, U-20, U-23, U-27, U-28 (helpers), U-29 handled and tested.

Context (a2e1201): `project.py` `NAME_RE` `:14`, `ProjectError` `:23`, `Project` `:27-30`, `repo_root` `:43-53`,
`_frontmatter` `:66-77`, `experiment_name` `:118-125`; `settings.py:13-28`; `tracking.py` `TrackingUnavailable` `:23`,
`preflight` `:33`, `tracked_run` `:49-67`; `conftest.py` `:9`, `:13-30`. pydantic, pyyaml, mlflow are already deps.

## Files (22)
New: `contracts/{EXPERIMENT.md,milestones.json,run_ledger_vectors.json,mlflow_tags.json}`,
`packages/datalab/src/datalab/{split,ledger_model,ledger_rules,ledger_ops,ledger,tags,tracking_queries}.py`,
`packages/datalab/tests/{test_split,test_ledger}.py`. Modified: `contracts/README.md`, `datalab/{project,tracking}.py`,
`packages/datalab/pyproject.toml`, `tests/{test_project,test_tracking}.py`, `decisions.md`, `ARCHITECTURE.md`, `.gitignore`.
`contracts/README.md` gets one bullet per new contract file and its readers (F-18).

### `contracts/EXPERIMENT.md` (new)
The one kind-agnostic contract (people, the skill, both code sides). Sections in order:
1. *Layout* — `configs/{train,eval}.yaml` + groups `paths/ data/ model/ experiment/ hparams_search/ (optional)`;
   `src/<pkg>/{train,eval}.py` (`@hydra.main(version_base=None)`), `python -m <pkg>.train|eval`; package rule: **`<pkg>` = `name.replace("-", "_")`, refused (exit 2, nothing written) when it is a
   Python keyword, in `sys.stdlib_module_names`, or in `set(importlib.metadata.packages_distributions()) | {"hydra",
   "omegaconf", "antlr4"}` (the import names of the env `datalab-new` runs in, plus the template's Hydra deps)**;
   candidates = `configs/model/<name>.yaml` (`_target_`), listed in `configs/experiment/<name>.yaml` `candidates:`;
   search grids in `configs/hparams_search/<name>.yaml` (`{<candidate>: {<param>: [values]}}`); no `--multirun`.
2. *Ledger* — `run.json` = `RunLedger` (I-1…I-15, V-1…V-3 in prose, check order below) + PROJECT.md narrative +
   `split.json`; ids and sequences only from `contracts/milestones.json`; no `skipped` status (U-18).
3. *split.json* — trouvetou schema + `split.py` rules; comparison: `grouped` (persona/question id), dev/test read as
   **train/test** (val may be empty). **Index lists address the rows of `paths.data_file`** (their union must be
   `range(len(rows))`, checked by the template loader); cleaning keeps row count and order — a drop becomes a filter
   applied after partitioning, never a removed line.
4. *Test isolation* — train reads train+val; `eval` alone reads test, only when `ledger.test_access_allowed` (current
   `audit`, audit `todo|produced`, split unchanged, a 2nd+ look on one `split_sha256` carries an expert note).
5. *MLflow* — URI only from `DATALAB_MLFLOW_TRACKING_URI`; experiment `<project>/<experiment.name>` (NAME_RE, `audit`
   reserved), eval in `<project>/audit`; one parent per invocation tagged `entry`, `split_sha256`, `data_sha256`,
   `score_on`; one child per grid combination, `run_name` `<family>-<i>`, tags `candidate`=family + `config_sha256`;
   only children log `metric.key` and `cost_usd`; no metric key token equals a candidate name; tag names only from
   `contracts/mlflow_tags.json`; one sweep at a time per server. After `report` is validated a new experiment archives
   run.json as for a kind change.
6. *Budget* — `project_spend` (all `<project>/*`, all statuses) is **shown** at the BOX ⏸️, never enforced (D-6).
**Reference:** `~/.claude/skills/trouvetou/CONTRACTS.md:7-173` (adapt; not the per-project sqlite store).

### `contracts/milestones.json` (new) — exact content
```json
{"schema_version": 1,
 "milestones": [{"id": "scoping", "agent": "ds-scoper"}, {"id": "dataset", "agent": "ds-dataset-finder"},
  {"id": "cleaning", "agent": "ds-data-cleaner"}, {"id": "eda", "agent": "ds-eda"},
  {"id": "features", "agent": "ds-feature-engineer"}, {"id": "modeling", "agent": "ds-modeler"},
  {"id": "audit", "agent": "ds-validator"}, {"id": "tracking", "agent": "ds-mlflow-tracker"},
  {"id": "report", "agent": "ds-reporter"}],
 "sequences": {"training": ["scoping", "dataset", "cleaning", "eda", "features", "modeling", "audit", "tracking", "report"],
  "comparison": ["scoping", "dataset", "eda", "modeling", "audit", "tracking", "report"]},
 "freeze_after": "dataset"}
```

### `contracts/mlflow_tags.json` (new) — exact content
`{"schema_version": 1, "tags": ["candidate", "split", "entry", "n_children", "n_failed", "failed_candidates", "test_look",
"split_sha256", "data_sha256", "score_on", "config_sha256"]}` — the single source of tag names (Python `datalab.tags`,
app `app/src/lib/tags.ts`; both suites compare to it).

### `contracts/run_ledger_vectors.json` (new)
**Shape:** `{"valid": [{"name", "run"}], "invalid": [{"name", "rule", "checked_by", "run"}]}`; every `run` a complete
literal object; each invalid run breaks exactly one rule, and `rule` is the first failure in the check order; `checked_by`
= `["python", "app"]` for `schema`, `U-13`, `I-1`, else `["python"]`. Structural only (V-1…V-3 are Python tests).
`T` = `{"status": "todo", "artifacts": [], "decision": null}`; `H(c)` = 64 × `c`; `V(m)` = `{"milestone": m,
"decision": "validate", "note": "ok"}`. Every base has keys in this order: `schema_version, kind, current_milestone,
milestones, dataset, metric, split_summary, split_sha256, data_sha256, features, winner, test_looks, decisions_log`.
- **B0** comparison fresh: `1`, `"comparison"`, `"scoping"`, 7 × `T`, `null`, `"score (max): mean task success on the
  dev personas"`, `null`, `null`, `null`, `null`, `null`, `[]`, `[]`.
- **B1** training mid-run: scoping/dataset/cleaning `validated`/`validate`, artifacts `["scope.md"]`, `["dataset.md"]`,
  `["src/demo/data/clean.py"]`; eda `produced` `["eda.md"]` null; rest `T`; current `eda`; dataset `{"id": "org/ds",
  "hash": "0123456789abcdef"}`; metric as B0; `"grouped seed 0: 60/20/20"`; `H(a)`; `null`; `null`; `null`; `[]`;
  log `[V(scoping), V(dataset), V(cleaning)]`.
- **B2** comparison at audit: B0 with scoping…modeling `validated`/`validate` (one artifact `<id>.md` each), audit
  `produced` `["audit.md"]`, current `audit`, dataset/split fields as B1, `data_sha256` `H(b)`, winner `{"candidate":
  "dummy", "run_id": "r1"}`, test_looks `[{"split_sha256": H(a), "run_id": "e1", "note": ""}]`, log `V(..)` × 4.

| name | built from | rule |
|---|---|---|
| valid `fresh-comparison` · `training-mid-run` · `audit-first-look` | B0 · B1 · B2 | — |
| valid `scoping-corrected` | B0, scoping `produced` `["scope.md"]` `correct`, log `[{scoping, correct, "narrow the metric"}]` | — |
| valid `comparison-complete` | B2, audit/tracking/report `validated` (`tracking.md`, `report.html`), current `report`, log × 7 | — |
| valid `after-redo` | B1 after `decide(eda, REDO, "leak", redo_from="dataset")`: dataset…report `T`, current `dataset`, dataset/split_summary/split_sha256 null, log + `{eda, redo, "leak"}` | — |
| `trouvetou-format` | B1 without `kind` | U-13 |
| `unknown-key` · `missing-dataset-key` · `empty-features` | B0 + `"notes": "x"` · B0 without `dataset` · B1 `features []` | schema |
| `skipped-status` · `schema-version-2` · `schema-version-true` | B0 report status `skipped` · `schema_version 2` · `true` | schema |
| `empty-metric` · `empty-dataset-hash` · `split-sha-uppercase` · `log-missing-note` | B0 `metric ""` · B1 hash `""` · B1 `H(A)` · B1 first log entry without `note` | schema |
| `milestone-outside-sequence` · `sequence-milestone-missing` | B0 + `features: T` · B0 without `report` | I-1 |
| `todo-with-decision` · `todo-with-artifacts` | B0 dataset decision `validate` · B0 dataset `["x.md"]` | I-2 |
| `validated-with-correct` · `produced-with-redo` | B1 scoping decision `correct` · B1 eda decision `redo` | I-3 |
| `produced-without-artifacts` · `produced-after-unvalidated` | B1 eda `[]` · B1 features `produced` `["f.md"]` | I-4 · I-5 |
| `current-not-first-unvalidated` · `comparison-with-features` | B1 current `cleaning` · B0 `features ["x"]` | I-6 · I-7 |
| `decision-without-log` · `log-decision-mismatch` | B1 log `[]` · B1 cleaning entry decision `correct` | I-8 |
| `log-unknown-milestone` · `no-split-hash-after-freeze` | B1 + `{foo, validate, "x"}` · B1 `split_sha256 null` | I-9 · I-10 |
| `dataset-validated-without-dataset` | B1 `dataset null` | I-11 |
| `artifact-escapes` · `artifact-absolute` · `artifact-backslash` · `artifact-drive-letter` | B1 scoping `["../x.md"]` · `["/etc/hosts"]` · `["docs\\x.md"]` · `["C:/x.md"]` | I-12 |
| `winner-before-modeling` · `modeling-validated-without-winner` | B1 + winner `{"candidate": "a", "run_id": "r"}` · B2 winner `null` | I-13 |
| `second-look-without-note` · `look-sha-uppercase` | B2 + look `{H(a), "e2", ""}` · B2 `test_looks[0].split_sha256` `H(A)` | I-14 · schema |
| `modeling-without-data-hash` | B2 `data_sha256 null` | I-15 |

### `packages/datalab/src/datalab/split.py` (new)
Frozen split model (trouvetou schema + data-lab rules) and its hash. Pure.
- `Partition(StrEnum)` `TRAIN="train"`, `VAL="val"`, `TEST="test"` · `SplitStrategy(StrEnum)` `RANDOM`, `STRATIFIED`,
  `TEMPORAL`, `GROUPED` (lowercase values) · `class SplitError(ValueError)` (names the file when there is one).
- `GroupBound`: `groups: tuple[str, ...]` · `TimeBound`: `time_max: str` (`datetime.fromisoformat` must parse) ·
  `PartitionSpec = tuple[NonNegativeInt, ...] | GroupBound | TimeBound` · `Splits`: `train`, `val`, `test`: `PartitionSpec`
  · `Split`: `strategy`, `seed: int`, `target`, `group_key`, `time_col: str | None`, `splits: Splits`. All models
  `ConfigDict(strict=True, extra="forbid", frozen=True)`, no defaults.
- `read_split(path: Path) -> Split` (bytes → `utf-8-sig` text → `Split.model_validate_json`; strict needs JSON mode;
  any error → `SplitError`) · `split_sha256(path: Path) -> str` (raw bytes) · `partition(split, which) -> PartitionSpec`.
- Model validator, distinct messages: one shape for all three; `GroupBound` ⇒ `grouped` + `group_key`; `TimeBound` ⇒
  `temporal` + `time_col`; no duplicates; partitions pairwise disjoint; `time_max` strictly increasing; train and test
  non-empty, val may be empty. **Reference:** `settings.py:13-28`; trouvetou `CONTRACTS.md:101-128`.

### `packages/datalab/src/datalab/ledger_model.py` + `ledger_rules.py` (new)
Pure. `ledger_model`: `Status(StrEnum)` `todo|produced|validated` · `Decision(StrEnum)` `validate|correct|redo` ·
`Kind(StrEnum)` `training|comparison` · `class LedgerError(ValueError)` · `@dataclass(frozen=True) Contract(agents:
Mapping[str, str], sequences: Mapping[Kind, tuple[str, ...]], freeze_after: str)` · `contract() -> Contract`
(`functools.cache`, `repo_root() / "contracts" / "milestones.json"`, `LedgerError` if unreadable or `set(Kind)` ≠ keys).
Models, `ConfigDict(strict=True, extra="forbid", frozen=True)`, **no defaults** (absent key = invalid, U-16):
`MilestoneEntry(status, artifacts: tuple[str, ...], decision: Decision | None)` · `Dataset(id, hash: str` min 1`)` ·
`LogEntry(milestone: str, decision: Decision, note: str` min 1`)` · `Winner(candidate, run_id: str` min 1`)` ·
`TestLook(split_sha256: str` `^[0-9a-f]{64}$`, `run_id: str` min 1, `note: str)` · `RunLedger(schema_version:
Literal[1]` (a `bool` refused), `kind, current_milestone: str, milestones: dict[str, MilestoneEntry], dataset: Dataset |
None, metric: str` min 1, `split_summary: str | None, split_sha256: str | None, data_sha256: str | None` (both
`^[0-9a-f]{64}$`), `features: tuple[str, ...] | None` (min 1), `winner: Winner | None, test_looks: tuple[TestLook, ...],
decisions_log: tuple[LogEntry, ...])`; method `sequence()`. One `@model_validator(mode="after")` calls
`ledger_rules.first_violation(self) -> str | None` and raises `PydanticCustomError("ledger_invariant", msg)`, so the
message is the bare `I-n: …` (a plain `ValueError` would read `Value error, I-n: …`).
**Check order (first failure wins; the app keeps the same order for what it checks):** (1) JSON decode → `invalid JSON:
…`; (2) an object without `kind` → `unsupported schema (kind missing)` (U-13); (3) field errors → `schema: <loc>: <msg>`
(pydantic error order = field order; zod declares the same order); (4) a `ledger_invariant` error → its bare message;
I-1…I-15 in number order:
I-1 keys == the kind's sequence (U-14) · I-2 `todo` ⇒ decision null, artifacts `()` · I-3 `validated` ⇒ `validate`,
`produced` ⇒ null|`correct` (U-1) · I-4 produced/validated ⇒ ≥ 1 artifact · I-5 non-`todo` ⇒ every earlier one
validated (U-2) · I-6 current = first non-validated, or the last when all are validated · I-7 comparison ⇒ `features`
null · I-8 a non-null decision = the decision of that milestone's last log entry · I-9 log milestones in the sequence ·
I-10 a milestone after `freeze_after` non-`todo` ⇒ `split_sha256` set (F-4) · I-11 `dataset` validated ⇒ `dataset` set ·
I-12 artifacts relative POSIX: no leading `/`, no `\`, no drive letter, no `..` segment (U-15) · I-13 `winner` set ⇔
`modeling` validated (U-27) · I-14 every look after the first on one `split_sha256` has a non-blank note (U-28) ·
I-15 `modeling` non-`todo` ⇒ `data_sha256` set (U-27). Each message starts with its id.

### `packages/datalab/src/datalab/ledger_ops.py` (new)
Pure transitions; each rebuilds via `_revalidate(data: dict) -> RunLedger` = `RunLedger.model_validate_json(json.dumps(
data))` (never `model_copy`; strict needs JSON mode; `ValidationError` → `LedgerError`).
- `new_ledger(kind: Kind, metric: str) -> RunLedger` — all `todo`, current = first, nullables null, tuples empty.
- `produce(l, milestone: str, artifacts: Sequence[str]) -> RunLedger` — must be current (`LedgerError`); `produced`,
  artifacts replaced, decision null.
- `decide(l, milestone, decision: Decision, note: str, *, redo_from: str | None = None, winner: Winner | None = None)`
  — milestone must be current and `produced`; appends `LogEntry`; `VALIDATE` → `validated`, current advances; `CORRECT`
  → stays `produced`; `REDO` → `redo(l, redo_from or milestone)` after the append; `redo_from` after `milestone` →
  `LedgerError`; `winner` required iff `milestone == "modeling"` and `VALIDATE` (else `LedgerError`).
- `redo(l, milestone) -> RunLedger` — unknown id → `LedgerError`; it and every later one → `T`; current = it; at or
  before `freeze_after` clears `split_sha256`, `split_summary`; at or before `dataset` clears `dataset`; at or before
  `features` clears `features`; at or before `modeling` clears `winner`, `data_sha256`. Log and test_looks untouched.
- `freeze_split(l, split_path: Path, summary: str)` — `freeze_after` validated and `split_sha256` null, else
  `LedgerError`; `read_split` must pass; sets `split_sha256`, `split_summary`.
- `record_data(l, data_path: Path)` — split frozen and `modeling` `todo`, else `LedgerError`; `data_sha256` = sha256 of
  the file bytes (the skill calls it at the BOX).
- `test_access_problem(l, split_sha: str, note: str | None) -> str | None` — in order: current ≠ `audit`; audit
  validated; `split_sha` ≠ `l.split_sha256`; a look on `split_sha` exists and `note` is blank → each a one-line reason
  · `test_access_allowed(l, split_sha, note=None) -> bool` = `problem is None` (U-28, F-21).
- `record_test_look(l, split_sha, run_id: str, note: str | None) -> RunLedger` — problem → `LedgerError`; appends
  `TestLook(split_sha, run_id, note or "")` · `look_number(l, split_sha) -> int` = 1 + looks on that sha.

### `packages/datalab/src/datalab/ledger.py` (new)
I/O, filesystem checks, hook CLI; re-exports the public names of `ledger_model`, `ledger_ops`, `split` (`__all__`).
- `parse(text: str) -> RunLedger` — strip one U+FEFF; steps (1)-(4) above; every failure → `LedgerError`.
- `read(project_dir: Path) -> RunLedger` — missing or corrupt → `LedgerError` naming `run.json`.
- `write_atomic(project_dir, l, *, replace_corrupt: bool = False) -> None` — re-validates via `_revalidate(
  l.model_dump(mode="json"))` (a `model_construct` object is refused before any write; `ValidationError` → `LedgerError`,
  F-6); with an existing run.json: refuse when its `decisions_log` or `test_looks` is not a prefix of the new one, or
  when its scoping is validated and `kind` differs (U-17); corrupt existing → `LedgerError` unless `replace_corrupt`;
  `json.dumps(..., indent=2, ensure_ascii=False) + "\n"`, milestones in sequence order; tmp `run.<token_hex(4)>.json.tmp`
  (mode `"x"`), flush, `os.fsync`, `os.replace`, dir fsync on POSIX; any exception → unlink tmp, re-raise.
- `validate_dir(project_dir) -> None` — split.json ⇒ `read_split` (→ `LedgerError`); run.json ⇒ `read` +
  V-1 each artifact of a non-`todo` milestone resolves inside `project_dir.resolve()` and exists; V-2 `split_sha256` set
  ⇒ split.json exists with that hash (F-4); V-3 `metric` starts with `f"{key} ({goal})"` of `project.card_metric(
  project_dir)`; neither file ⇒ ok (U-23).
- `main(argv=None) -> int` — `python -m datalab.ledger validate PATH...`; `run.json`/`split.json` paths (existing or
  deleted) → parent dir, a dir → itself; absolute, deduped, sorted; `ok <dir>` (stdout) / `FAIL <dir>: <msg>` (stderr);
  exit 0 / 1 any FAIL / 2 usage or missing dir. No console script; no `print` outside `main`.
**Reference:** `new_project.py:72-77` (atomic publish), `:56-83` (exit codes).

### `datalab/{project,tags}.py`, `packages/datalab/pyproject.toml` (modify / new / modify)
- `project.py`: `METRIC_KEY_RE: Final = re.compile(r"^[A-Za-z0-9_.\-/]+$")` (identical literal `app/src/lib/card.ts:8`);
  `@dataclass(frozen=True) CardMetric(key: str, goal: Literal["max", "min"])`; `card_metric(project_dir: Path) ->
  CardMetric` — `_frontmatter(project_dir / "PROJECT.md")["metric"]`; absent, bad key or goal → `ProjectError` naming the card.
- `tags.py`: `class Tag(StrEnum)` with the 11 names of `mlflow_tags.json` (`CANDIDATE = "candidate"`, …).
- `packages/datalab/pyproject.toml`: contract `:38-42` becomes `name = "pure modules stay pure (no weaviate/mlflow)"`, `source_modules = ["datalab.project",
"datalab.split", "datalab.ledger_model", "datalab.ledger_rules", "datalab.ledger_ops", "datalab.ledger", "datalab.tags"]`.

### `packages/datalab/src/datalab/tracking.py` + `tracking_queries.py` (modify / new)
`tracking.py` (keep `tracked_run`'s signature):
- `class TrialError(RuntimeError)` · `@dataclass Trial(run_id: str, candidate: str, cost_usd: float = 0.0)`;
  `add_cost(usd)` refuses non-finite/negative (`ValueError`), adds, logs the cumulative `cost_usd` at once.
- Registry: `_OUTCOMES: dict[str, _Outcome]` keyed by parent run id (`_Outcome(children: int, failed: list[str])`),
  written by `tracked_trial`, **popped by `tracked_run`**; `_OPEN` slot + `threading.Lock` for the open trial.
- `@contextmanager tracked_trial(run_name: str, tags: Mapping[str, str] | None = None, *, candidate: str | None = None)
  -> Iterator[Trial]` — order: (1) `project` or `candidate` in tags → `ValueError`; (2) no active run → `TrialError`;
  (3) a trial already open (nesting, threads, asyncio) → `TrialError`; (4) parent via `MlflowClient().get_run`, no
  `project` tag → `TrialError`; (5) `start_run(run_name, nested=True, experiment_id=<parent's>)`, tags `{"project":
  <parent's>, Tag.CANDIDATE: candidate or run_name} | extra`; yields; `finally: try: log cost_usd finally: free
  _OPEN, record the outcome` (the inner `finally` survives a failing `cost_usd` log); an exception marks the child
  FAILED and is re-raised.
- `tracked_run`: `try/finally` around `yield`; pops `_OUTCOMES[run_id]`; only if present tags `n_children`, `n_failed`
  (str ints), `failed_candidates` (sorted run names, comma-joined, `""` if none). No `cost_usd`.
`tracking_queries.py` (re-exported from `tracking`):
- `project_spend(project, settings) -> float` — experiments via `search_experiments(view_type=ALL, filter_string=f"name
  LIKE '{name}%'")` (paginated; name checked by `experiment_name` first), kept when `== p` or `startswith(p + "/")`
  (mirrors `app/src/lib/mlflow.ts:87,93-94`); **none → 0.0 with no `search_runs` call**; runs via `search_runs(ids,
  filter_string=f"tags.project = '{name}'", run_view_type=ALL, max_results=1000, page_token=…)`; sum of `cost_usd`
  over every status incl. RUNNING (unlike `projects/voice-arch/src/voice_arch/budget.py:11`, ADR).
- `@dataclass(frozen=True) StaleRun(run_id, run_name, experiment, start_time: datetime)` · `stale_runs(project,
  settings, older_than: timedelta, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> list[StaleRun]` —
  RUNNING, `start_time < now() - older_than`, sorted by id; `older_than <= 0` → `ValueError`. Lists only.
- `close_runs(project, settings, run_ids: Sequence[str]) -> list[str]` — every id RUNNING and tagged `project`, else
  `ValueError` before any change; `set_terminated(id, status="KILLED")`; returns sorted ids (F-9, after confirmation).
**Reference:** `projects/voice-arch/src/voice_arch/budget.py:22-39` (pagination loop).

### `packages/datalab/tests/test_split.py` (new)
Fixture `_split(**overrides) -> dict` (random, seed 0, target `y`, `[0,1,2]/[3]/[4]`), written under `tmp_path`.

| Test | Given → expected | Source |
|---|---|---|
| `test_f_4_overlapping_groups_rejected` | grouped `persona`, train `{"groups": ["a","b"]}`, test `["b"]` → `SplitError` mentioning `b` | F-4 |
| `test_f_4_grouped_and_temporal_shapes_accepted` | groups `a`/`b`/`c` → parses; temporal `t`, `2024-01-01` < `2024-06-01` < `2024-12-31` → parses | F-4 |
| `test_overlapping_indices_rejected` · `test_temporal_bounds_not_increasing_rejected` | train `[0,1]`, val `[1]` → `SplitError` · val time_max == test's → `SplitError` | F-4 |
| `test_empty_test_rejected` | test `[]` → `SplitError`; val `[]` → parses (comparison) | U-30 |
| `test_mixed_shapes_rejected` · `test_grouped_without_group_key_rejected` | indices + groups → `SplitError` · grouped, `group_key null` → `SplitError` | default |
| `test_split_sha256_is_raw_bytes_hash` · `test_read_split_strips_bom` · `test_split_seed_string_rejected` | bytes `b'{"x":1}'` → `hashlib.sha256(b'{"x":1}').hexdigest()` · BOM file → parses · `"seed": "0"` → `SplitError` (strict) | F-4, F-20 |

### `packages/datalab/tests/test_ledger.py` (new)
`VECTORS` from `REPO_ROOT / "contracts" / "run_ledger_vectors.json"`; `_vector(name)`; `_project(tmp_path, run, files)`
writes PROJECT.md (`metric: {key: score, goal: max}`), run.json, artifacts; splits from `test_split._split`.

| Test | Given → expected | Source |
|---|---|---|
| `test_f_18_ledger_vectors[<name>]` (parametrized, ids = vector names; covers U-1, U-2, U-13, U-14, U-16, I-1…I-15) | each `valid` → `parse(json.dumps(run))` ok and `model_dump(mode="json") == run`; each `invalid` → `LedgerError` whose message starts with `rule` (`schema` → `schema:`, U-13 → `unsupported schema (kind missing)`) | F-18 |
| `test_contract_matches_kind_enum` | `set(contract().sequences) == {"training","comparison"}`; 9 / 7 ids | default |
| `test_u_2_redo_resets_later_milestones_to_todo` | B1 + `redo(l, "dataset")` == vector `after-redo` minus its last log entry | U-2 |
| `test_decide_validate_advances_current` · `test_decide_correct_then_produce_resets_decision` | B0 scoping produced → `VALIDATE` → validated, current `dataset`, log 1 · `CORRECT` → `produced`/`correct`; `produce` → decision null | U-2, U-1 |
| `test_decide_redo_from_modeling_at_audit` | B2 → `decide(l, "audit", REDO, "leak", redo_from="modeling")` → modeling + audit `todo`, current `modeling`, `winner`/`data_sha256` null, last log `{audit, redo}` | U-2 |
| `test_decide_modeling_requires_winner` | comparison at modeling produced → `VALIDATE` without winner → `LedgerError`; with `Winner("dummy","r1")` → set | U-27 |
| `test_produce_refuses_non_current_milestone` · `test_decide_refuses_non_produced_milestone` | B0 → `produce(l, "eda", ["x"])` → `LedgerError` · B0 → `decide(l, "scoping", VALIDATE, "ok")` → `LedgerError` | U-2 |
| `test_decide_refuses_redo_from_after_milestone` · `test_redo_unknown_milestone_refused` | B1 → `decide(l, "eda", REDO, "x", redo_from="features")` → `LedgerError` · `redo(B1, "foo")` → `LedgerError` | U-2 |
| `test_freeze_split_before_dataset_validated_refused` | B0 + valid split file → `LedgerError`; split fields still null | F-4 |
| `test_u_16_scoping_ledger_with_null_dataset_is_valid` | `new_ledger(COMPARISON, "m")` → `dataset is None`, round-trips `parse` | U-16 |
| `test_f_5_unknown_key_rejected_not_dropped` | `unknown-key` → message contains `notes` | F-5 |
| `test_f_5_read_corrupt_raises_ledger_error` · `test_read_missing_run_json_raises` | `{"schema_version": 1,` → `LedgerError` naming `run.json` · empty dir → `LedgerError` naming `run.json` | F-5 |
| `test_u_28_test_access_rules` | B2 + `H(a)`: note None → `test_access_problem` mentions `note`; `"why"` → None; `H(c)` → mentions `split.json`; B1 → mentions `audit`; `look_number(B2, H(a)) == 2` | U-28 |
| `test_record_test_look_appends` | B2, `record_test_look(l, H(a), "e2", "re-check after fix")` → 2 looks, last note kept; note None → `LedgerError` | U-28 |
| `test_record_data_hashes_file_and_requires_freeze` | at modeling `todo` with split frozen → `data_sha256 == sha256(bytes)`; B0 → `LedgerError` | U-27 |
| `test_f_4_split_changed_after_freeze_fails_validate` | `freeze_split`, run.json written, one index moved in split.json → `validate_dir` `LedgerError` with `V-2` | F-4 |
| `test_u_23_validate_accepts_split_without_run_json` | only split.json → `validate_dir` None; `main(["validate", str(d)]) == 0` | U-23 |
| `test_u_15_missing_artifact_fails_validate` · `test_artifact_symlink_escape_rejected` | produced `eda.md` absent → `V-1` + `eda.md` · `scope.md` → symlink outside → `V-1` (skip win32) | U-15 |
| `test_metric_not_matching_card_fails_validate` | card `score`/`max`, run.json metric `"loss (min): x"` → `V-3` | U-29 |
| `test_f_6_serializer_failure_leaves_run_json_byte_identical_and_no_tmp` · `test_f_6_invalid_model_never_written` | patch `datalab.ledger.json.dumps`, then `os.fsync`, to raise → bytes identical, no `*.json.tmp` · `RunLedger.model_construct(...)` with a todo decision → `LedgerError` (not `ValidationError`), no run.json | F-6 |
| `test_write_refuses_rewritten_log_or_looks` | on-disk log of 2, first note changed → `LedgerError`; B2 on disk, new ledger with `test_looks ()` → `LedgerError` | U-2 |
| `test_write_refuses_kind_change_after_scoping_validated` · `test_parse_strips_bom` | comparison, scoping validated on disk, new `training` → `LedgerError` · `"\ufeff" + json.dumps(B0)` → parses | U-17, F-20 |
| `test_main_maps_file_paths_to_dirs` | `[f"{d}/run.json", f"{d}/split.json"]` → `d` once, 0; missing dir → 2; invalid run.json → 1 | F-1 |

### `packages/datalab/tests/test_project.py` (modify)
| Test | Given → expected | Source |
|---|---|---|
| `test_card_metric_reads_frontmatter` | `metric: {key: score, goal: max}` → `CardMetric("score", "max")`; no metric, key `a b`, goal `up` → `ProjectError` | U-29 |
| `test_metric_key_re_matches_app_literal` | literal captured by `re.search(r"METRIC_KEY_RE = /(.+)/;", card_ts)` == `METRIC_KEY_RE.pattern` (both directions: equal strings) | F-18 |

### `packages/datalab/tests/test_tracking.py` (modify)
Reuse `_project`, `_settings` (`:15-20`), `sqlite_uri`; parents run in experiment `p/e1`; read with `MlflowClient`.

| Test | Given → expected | Source |
|---|---|---|
| `test_parent_logs_no_cost_usd` | children `a` (0.25) and `b` (0.5) → parent lacks `cost_usd`; `project_spend == 0.75` | F-7, D-5 |
| `test_f_7_failed_child_still_logs_cost_usd` | child adds 0.1 then raises → FAILED, `cost_usd 0.1`; next child opens fine | F-7 |
| `test_f_7_budget_counts_running_runs` | RUNNING run 0.4 + FINISHED child 0.1 in `p/x` + 9.0 in sibling `p-x` → `0.5` | F-7 |
| `test_project_spend_without_experiment_is_zero` | empty store, `MlflowClient.search_runs` patched to raise → `0.0` | F-7 |
| `test_f_8_parent_lists_failed_candidates` | `a` ok, `b` raises → parent `n_children "2"`, `n_failed "1"`, `failed_candidates "b"`; `_OUTCOMES == {}` after; a plain `tracked_run` gets no count tags (U-12) | F-8 |
| `test_f_9_stale_runs_listed_not_closed` · `test_f_9_close_runs_kills_only_given_ids` | RUNNING at now−48 h and now−1 h, `now` injected → `stale_runs(.., 24 h)` = old id only, both still RUNNING · `close_runs(p, s, [old])` → `[old]` KILLED, other RUNNING; a FINISHED id → `ValueError`, nothing changed; `stale_runs(.., timedelta(0))` → `ValueError` | F-9 |
| `test_f_14_child_in_parent_experiment_after_set_experiment` · `test_f_14_trial_refuses_project_or_candidate_tag` | in a `p/e1` parent, `set_experiment("other")`, then a trial → same `experiment_id`, `mlflow.parentRunId` == parent · `tags={"project": "x"}`, `tags={"candidate": "x"}` → `ValueError`; no child | F-14 |
| `test_trial_without_parent_refused` · `test_u_20_tracked_trial_refuses_nested_trial` | no active run → `TrialError` · trial in a trial → `TrialError`, outer FINISHED | F-14, U-20 |
| `test_f_15_concurrent_trial_refused` · `test_trial_slot_freed_when_cost_log_fails` | `asyncio.gather` of two trials under one parent (first awaits `sleep(0)` inside) → one `TrialError` · `mlflow.log_metric` patched to raise once in the trial's `finally` → the error propagates, then a new trial opens, and the parent still gets `n_children "1"` | F-15 |
| `test_u_10_trial_name_and_candidate` · `test_add_cost_rejects_negative_and_nan` | `tracked_trial("hist-gb-0", candidate="hist-gb")` → run_name `hist-gb-0`, tag `candidate "hist-gb"`; no `candidate` → tag = run_name · `-1.0`, `nan` → `ValueError`, cost unchanged | U-10, F-7 |
| `test_tag_names_match_contract` | `{t.value for t in Tag}` == set of `mlflow_tags.json` `tags`, 11 entries | F-18 |

### `decisions.md` (modify — append ADR)
`## 2026-11-06 — Experiment methodology: trouvetou in data-lab` · accepted · Context: voice-arch lessons. Decision:
Hydra in the template; MLflow 5050 (D-1); metric + cost on children only (D-5); `<project>/<experiment.name>`, eval in
`<project>/audit`; grid in-process (D-4); run.json + PROJECT.md, strict order, `redo` reset, no `skipped`; test gated,
looks counted; winner in run.json, card best on frozen split + full data; budget shown, not enforced (D-6); one sweep per
server (F-16); spend counts RUNNING. Alternatives: per-project sqlite, role tag, `ledger.md`, multirun + Postgres, hard
budget stop. Consequences: one sweep per server; legacy runs stay flat.

### `ARCHITECTURE.md` + `.gitignore` (modify)
ARCHITECTURE: `## Cross-phase contracts` (`:286`) run.json/split.json, the 3 JSON contracts, nested-run + tag rules,
naming; `## Key Domain Concepts` (`:265`) *Experiment ledger*; `## State Machines` (`:273`) `todo → produced →
validated`, `produced → produced` (correct), redo of m → m and later `todo`; `## Project Structure` (`:37`) new files.
`.gitignore:1` (`# Python`): add `*.json.tmp` (`# datalab.ledger.write_atomic temp files (F-6)`).

<!-- plan-validate: READY 2026-11-06 sha256:a75bcdf032ee -->
