# Agent overrides

The ds-* agents (`~/.claude/agents/ds-*.md`) were written for trouvetou. Paste the common block into every dispatch,
then the agent's row below: where an agent's own file and this page disagree, this page wins.

## Common block (paste into every dispatch)

```text
data-lab overrides (they win over your agent file):
- MLflow: the URI comes only from DATALAB_MLFLOW_TRACKING_URI (the shared server, port 5050, D-1). Never write a
  tracking URI into a config, never create a local mlruns/ or mlflow.db.
- Experiments: <project>/<experiment.name>; eval runs go to <project>/audit (reserved).
- One parent run per invocation; one child per grid combination, run name <family>-<i>, tag candidate = the family.
  Only children log the card's metric.key and cost_usd. No metric key carries a candidate name.
- Every paid call (API, hosted model) runs inside a datalab.tracking.tracked_trial, so its cost is logged.
- Work in projects/<name>/ (its own uv env): uv run python -m <pkg>.train experiment=<name> [hparams_search=<grid>].
- You never edit src/ or tests/: return a code spec and the orchestrator routes it through /implement-phase + /check.
  YAML under configs/ and Markdown artifacts are yours to write.
- The narrative goes in PROJECT.md (the orchestrator appends it); there is no project.md.
- The budget is shown to the expert at the BOX only; you never enforce or stop on it.
- No credentials anywhere: configs, run.json, MLflow params/tags/artifacts, Markdown, reports.
```

## Per-agent rows

| Agent | trouvetou behaviour (cite) | data-lab override |
|-------|----------------------------|-------------------|
| all agents | trouvetou `SKILL.md:36-63` (Step 0) copies `assets/` (compose file, requirements) into the project | nothing is copied into the project: `datalab-new` scaffolded it and the shared stack runs from the repo root |
| `ds-mlflow-tracker` | `ds-mlflow-tracker.md:18`: `tracking_uri` from `configs/logger/mlflow.yaml`, default `sqlite:///mlflow.db` | no `logger/` group exists; the URI comes from `DATALAB_MLFLOW_TRACKING_URI`, never a local `mlruns/`; verify the runs `train.py` logged, do not re-log trials; results in `tracking.md` |
| `ds-validator` | `ds-validator.md:18` and `:29`: re-scores the frozen test itself via `src/<project>/eval.py` | only `uv run python -m <pkg>.eval`, which the ledger gates (`test_access_problem`); a second look needs the expert's `look_note`, which only the orchestrator obtains; results in `audit.md` |
| `ds-modeler` | `ds-modeler.md:24-25`: runs its own bounded search and logs every trial its own way; `:30` the budget is a hard stop | trials are the children `train.py` makes; it edits `configs/model/*`, `configs/experiment/*`, `configs/hparams_search/*` (grid lists only); it never enforces a budget; code it needs goes through the plan route |
| `ds-modeler` | `ds-modeler.md:35`: runs `<skill-assets>/check_hydra_project.py` | the orchestrator runs `python3 tools/pre_commit_checks/hydra_gate.py projects/<name>` after modeling |
| `ds-data-cleaner`, `ds-feature-engineer` | `ds-data-cleaner.md:14`, `ds-feature-engineer.md:14`: pipeline code in `src/<project>/data/clean.py`, `src/<project>/features/build.py` | a code spec in `cleaning.md` / `features.md`, routed through `/plan-features` + `/implement-phase` + `/check` (SKILL.md section 13) |
| `ds-data-cleaner` | `ds-data-cleaner.md:42`: documents every dropped row | `data/clean/data.jsonl` keeps the row count and order of the file `split.json` indexes; a drop is a filter column/flag applied after partitioning, never a removed line (the template loader refuses a split that does not cover the rows) |
| `ds-eda` | `ds-eda.md:28`: plotting code in `src/<project>/eda.py` | figures under `figures/` and findings in `eda.md`; plotting code, if it must persist, is a code spec |
| `ds-reporter` | `ds-reporter.md:27`: reads `run.json` / `project.md` | reads `PROJECT.md` + `run.json`, writes `projects/<name>/reports/report.html` |
