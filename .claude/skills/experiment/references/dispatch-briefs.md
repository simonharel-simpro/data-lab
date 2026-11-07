# Dispatch briefs

One brief per milestone id of `contracts/milestones.json`. Fill the placeholders, paste the brief, then the common
block and the agent's row from `agent-overrides.md`. `{metric}` is the `metric` string of `run.json`, restated word
for word. Every path is under `projects/<name>/`; `<pkg>` is the project's package (`<name>` with `-` → `_`).

Fields every brief carries: **Inputs**, **Metric**, **Deliverable**, **Allowed reads**, **Forbidden**, **Return**.
Forbidden in every brief: editing `src/` or `tests/` (ask for code as a spec instead), recomputing or rewriting the
split, a tracking URI in any config, `--multirun`, a metric key carrying a candidate name.

## scoping — `ds-scoper`

- **Inputs:** `PROJECT.md` (Objectif, the card `metric`), the expert's framing.
- **Metric:** `{metric}`. Confirm it is gradable, or say why it is a misleading proxy.
- **Deliverable:** `scope.md`.
- **Allowed reads:** no data rows. If data already exists, only the names of the target, group_key and time_col.
- **Forbidden:** the common list; choosing a dataset or a model.
- **Return:** the `scope.md` structure of `ds-scoper.md:37-56` (problem type, training type, metric(s), constraints,
  out of scope, assumptions, leakage risks).

## dataset — `ds-dataset-finder`

- **Inputs:** `PROJECT.md`, `scope.md`.
- **Metric:** `{metric}`. Can it be computed on each candidate?
- **Deliverable:** `dataset.md`: the candidate comparison, the recommendation with its Hub id and revision sha, and a
  proposed split (strategy, seed, target, group_key, time_col; for a comparison `grouped` by persona or question id).
- **Allowed reads:** dataset cards and schemas; of the rows, only the target, group_key and time_col columns.
- **Forbidden:** the common list; downloading the data (the orchestrator acquires it after the expert's validate).
- **Return:** the structure of `ds-dataset-finder.md:37-48` (candidates table, recommendation, if nothing fits).

## cleaning — `ds-data-cleaner`

- **Inputs:** `PROJECT.md`, `scope.md`, `dataset.md`, `split.json`, `data/raw/data.jsonl`.
- **Metric:** `{metric}`.
- **Deliverable:** `cleaning.md` (diagnosis, transforms, the code spec for the cleaning module), knobs in
  `configs/data/*.yaml`; after the code route (SKILL.md section 13), `data/clean/data.jsonl`.
- **Allowed reads:** the train and val rows of `split.json`; every statistic is fit on train.
- **Forbidden:** the common list. Keep the row count and order of the file `split.json` indexes; a drop is a
  post-split filter (a flag column), never a removed line.
- **Return:** the structure of `ds-data-cleaner.md:48-59` (diagnosis, transforms, dropped, outputs with rows in/out).

## eda — `ds-eda`

- **Inputs:** `PROJECT.md`, `scope.md`, `dataset.md`, `split.json`, `data/clean/data.jsonl` (a comparison:
  `paths.data_file`, the same path).
- **Metric:** `{metric}`. Say if a finding means the metric should change.
- **Deliverable:** `eda.md` and `figures/`.
- **Allowed reads:** the train and val rows of `split.json`.
- **Forbidden:** the common list; plotting code under `src/` (spec it instead).
- **Return:** the structure of `ds-eda.md:40-50` (3-5 findings with implications, leakage/bias flags, figures).

## features — `ds-feature-engineer`

- **Inputs:** `PROJECT.md`, `scope.md`, `split.json`, `eda.md`, `data/clean/data.jsonl`.
- **Metric:** `{metric}`.
- **Deliverable:** `features.md` (the final feature list, the leakage check, the code spec for the pipeline), knobs
  under `configs/`.
- **Allowed reads:** the train and val rows of `split.json`; every transform is fit on train.
- **Forbidden:** the common list.
- **Return:** the structure of `ds-feature-engineer.md:36-49` (feature list table, dropped, target-leakage check,
  pipeline).

## modeling — `ds-modeler`

- **Inputs:** `PROJECT.md`, `scope.md`, `split.json`, `eda.md`, `features.md` (training), `data/clean/data.jsonl`.
- **Metric:** `{metric}`. The card key is the only ranking key.
- **The validated BOX:** candidates `<list>` (`configs/model/*.yaml`, `configs/experiment/<name>.yaml`
  `candidates:`), grid `configs/hparams_search/<grid>.yaml`, child count `<n>`, displayed budget `<usd>` (shown only,
  never a stop).
- **Run:** `cd projects/<name> && uv run python -m <pkg>.train experiment=<name> hparams_search=<grid>` (omit
  `hparams_search=` when there is no grid). One invocation = one parent run, one child per combination.
- **Deliverable:** `modeling.md` (baseline gate, leaderboard of the children, proposed winner, risks),
  `configs/experiment/<name>.yaml`, `configs/hparams_search/<grid>.yaml`.
- **Allowed reads:** the train and val rows of `split.json` (train reads them; nothing else).
- **Forbidden:** the common list; changing the BOX without asking.
- **Return:** the structure of `ds-modeler.md:44-60` (candidates, baseline gate, leaderboard, winner with its child
  run id, risks, outputs).

## audit — `ds-validator`

- **Inputs:** `PROJECT.md`, `scope.md`, `split.json`, `modeling.md`, `run.json`.
- **Metric:** `{metric}`.
- **Winner:** family `<family>`, child run id `<run id>`, params `<k=v ...>`; the leaderboard (FINISHED children).
- **Posture:** fresh context, try to break the winner.
- **Deliverable:** `audit.md`.
- **Allowed reads:** train and val as before; the test partition only through
  `cd projects/<name> && uv run python -m <pkg>.eval` (grid winner: `model=<family> model.<k>=<v> ...`).
- **Look rule:** one look per split. Before a second eval call, stop and return to the orchestrator: a further look
  needs the expert's note, passed as `"look_note='<reason>'"`. Never tune on what the test shows.
- **Forbidden:** the common list; reading test rows any other way; retraining.
- **Return:** the structure of `ds-validator.md:40-55` (verdict per dimension, frozen-test re-score, overall).

## tracking — `ds-mlflow-tracker`

- **Inputs:** `PROJECT.md`, `scope.md`, `run.json`, `modeling.md`, `audit.md`.
- **Metric:** `{metric}`. Best = by the card key among FINISHED children.
- **Deliverable:** `tracking.md`.
- **Allowed reads:** MLflow runs of `<name>/*` through `DATALAB_MLFLOW_TRACKING_URI`; no data rows.
- **Forbidden:** the common list; re-logging trials; closing or deleting runs.
- **Return:** the structure of `ds-mlflow-tracker.md:36-48` (experiments, run comparison, best, registry).

## report — `ds-reporter`

- **Inputs:** `PROJECT.md`, `run.json`, `scope.md`, `dataset.md`, `split.json`, `eda.md`, `features.md` (training),
  `modeling.md`, `audit.md`, `tracking.md`.
- **Metric:** `{metric}`.
- **Deliverable:** `reports/report.html` (self-contained).
- **Allowed reads:** the artifacts above; no data rows.
- **Forbidden:** the common list; a number that is not on disk.
- **Return:** per `ds-reporter.md:55`, the report path and a 2-line summary.
