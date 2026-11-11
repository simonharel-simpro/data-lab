# Experiment contract (kind-agnostic)

One contract for people, the `/datalab:experiment` skill and both code sides (the `datalab` package and the app). It adapts
trouvetou's `CONTRACTS.md` to data-lab: the same milestones and ledger, but one shared MLflow server instead of a
per-project sqlite store (D-1), and a ledger that can say `kind: training | comparison | exploration`.

## 1. Layout

- `configs/{train,eval}.yaml` plus the groups `paths/ data/ model/ experiment/ hparams_search/` (the last is optional).
- `src/<pkg>/{train,eval}.py`, each `@hydra.main(version_base=None)`, run as `python -m <pkg>.train|eval`.
- Package rule: **`<pkg>` = `name.replace("-", "_")`, refused (exit 2, nothing written) when it is a Python keyword,
  in `sys.stdlib_module_names`, or in `set(importlib.metadata.packages_distributions()) | {"hydra", "omegaconf",
  "antlr4"}`** (the import names of the env `datalab-new` runs in, plus the template's Hydra deps).
- Candidates are `configs/model/<name>.yaml` (each with a `_target_`), listed in `configs/experiment/<name>.yaml`
  under `candidates:`. Search grids live in `configs/hparams_search/<name>.yaml` as
  `{<candidate>: {<param>: [values]}}`. There is no `--multirun`: the grid runs in-process (D-4).

## 2. Ledger

`run.json` is a `RunLedger` (`datalab.ledger_model`): invariants I-1 to I-15 and the filesystem checks V-1 to V-3,
evaluated in this order, the first failure wins:

1. JSON decode: `invalid JSON: ...`
2. an object without `kind`: `unsupported schema (kind missing)` (a trouvetou-format file, U-13)
3. field errors: `schema: <loc>: <msg>` (pydantic and zod list fields in the same order)
4. invariants I-1 to I-15 in number order, each message starting with its id.

Milestone ids and the three sequences come only from `contracts/milestones.json`; there is no `skipped` status (U-18).
The ledger sits beside the PROJECT.md narrative and `split.json`. `contracts/run_ledger_vectors.json` holds the shared
cases (`checked_by` says which side must refuse an invalid one); V-1 to V-3 are Python-only.

An exploration (`scoping → eda → report`) has no dataset step, split, modeling, audit or tracking: its `dataset`,
`split_sha256`, `split_summary`, `features`, `winner` and `data_sha256` stay null and `test_looks` empty (I-7, I-10,
I-11, I-13, I-14, I-15). Its runs, if any, come from project code via `datalab.tracking` (the template train/eval
refuse it), and the card ranks them like a project without run.json (D-5, D-6).

## 3. split.json

The trouvetou schema plus the rules of `datalab.split`. For a comparison the dev and test partitions read as
**train** and **test** (`val` may be empty), and the split is `grouped` by persona or question id.
**Index lists address the rows of `paths.data_file`**: their union must be `range(len(rows))`, which the template
loader checks. Cleaning keeps row count and order: a drop becomes a filter applied after partitioning, never a removed
line.

## 4. Test isolation

`train` reads train and val. `eval` alone reads test, and only when `ledger.test_access_allowed` holds: the current
milestone is `audit`, the audit is `todo` or `produced`, the split is unchanged, and a second or later look on one
`split_sha256` carries an expert note (U-28, F-21).

## 5. MLflow

- The URI comes only from `DATALAB_MLFLOW_TRACKING_URI`.
- Experiment `<project>/<experiment.name>` (NAME_RE, `audit` reserved); eval runs go to `<project>/audit`.
- One parent run per invocation, tagged `entry`, `split_sha256`, `data_sha256`, `score_on`; one child per grid
  combination, `run_name` `<family>-<i>`, tags `candidate` (= the family) and `config_sha256`.
- Only children log `metric.key` and `cost_usd`; no metric key token equals a candidate name.
- Tag names come only from `contracts/mlflow_tags.json` (`datalab.tags.Tag`, `app/src/lib/tags.ts`).
- One sweep at a time per MLflow server (F-16). After `report` is validated, a new experiment archives run.json the
  way a kind change does.

## 6. Budget

`project_spend` (every `<project>/*` experiment, every run status, RUNNING included) is **shown** at the BOX pause and
never enforced (D-6).
