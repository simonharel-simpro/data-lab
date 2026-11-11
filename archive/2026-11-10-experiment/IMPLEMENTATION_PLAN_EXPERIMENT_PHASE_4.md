# Phase 4 — `/experiment` skill

**Agent:** `general-purpose` (Markdown only; no Python beyond what Phases 1-3 provide) · **Depends on:** Phases 1, 2, 3 ·
**Plan:** `IMPLEMENTATION_PLAN_EXPERIMENT.md`

**Acceptance:** this phase ships no code, so it has **no unit tests**. Its acceptance is the **dry-run walkthrough
checklist** at the end: a reviewer reads the three files and walks a scratch project through them, then tears it down;
every check must pass. U-2 (demotion), U-17, U-24, U-27/U-28 (skill side), F-7 (display), F-9 (skill side) are verified there.

Already exists from Phase 1 (`from datalab import ledger`): `ledger.read(dir)`, `write_atomic(dir, l, *,
replace_corrupt=False)` (refuses a rewritten decisions_log/test_looks and a kind change after validated scoping),
`new_ledger(kind, metric)`, `produce(l, m, artifacts)`, `decide(l, m, decision, note, *, redo_from=None, winner=None)`
(`winner=ledger.Winner(candidate, run_id)` required when validating `modeling`), `redo(l, m)`, `freeze_split(l,
split_path, summary)`, `record_data(l, data_path)`, `test_access_problem(l, split_sha, note)`, `look_number(l,
split_sha)`, enums `Kind`, `Decision`, `Status`; CLI `python -m datalab.ledger validate projects/<name>` (exit 0/1/2;
V-3: run.json `metric` starts with `<card metric.key> (<goal>)`); `datalab.tracking.project_spend(project, settings)`,
`stale_runs(project, settings, older_than)` (lists only), `close_runs(project, settings, run_ids)`;
`contracts/{milestones,mlflow_tags}.json`, `contracts/EXPERIMENT.md`. From Phase 2: hooks `hydra-gate` + `ledger`, CI
matrix. From Phase 3: every `datalab-new` project has `configs/{train,eval}.yaml` + groups `paths, data, model,
experiment, hparams_search (optional)`; `python -m <pkg>.train experiment=<name> [hparams_search=<grid>]` (1 parent in
`<project>/<experiment.name>`, one child `<family>-<i>` per grid combination, train+val only, exit 2 on a grid naming an
unknown candidate); `python -m <pkg>.eval [look_note="…"]` (winner by default; refused unless current = `audit`; a 2nd+
look on one split needs `look_note`; refused when the config hash differs from the winner child's).
Source being adapted: `~/.claude/skills/trouvetou/SKILL.md` (221 lines), `CONTRACTS.md`; agents `~/.claude/agents/ds-*.md`.

## Files (3)
New: `.claude/skills/experiment/SKILL.md`, `.claude/skills/experiment/references/dispatch-briefs.md`,
`.claude/skills/experiment/references/agent-overrides.md`. Nothing else.

### `.claude/skills/experiment/SKILL.md` (new)
**Frontmatter:** `name: experiment`; `description:` one sentence — run a data-lab experiment milestone by milestone with
the ds-* specialists, stopping for expert validation at each step (`projects/<name>`, run.json ledger, frozen split,
shared MLflow).
**Sections, in this order:**
1. *What this is* — adapts trouvetou; a table of differences: shared MLflow (`DATALAB_MLFLOW_TRACKING_URI`, D-1) instead
   of per-project sqlite; no Step 0 asset copy (trouvetou `SKILL.md:36-63`); `projects/<name>`, uv, `python -m <pkg>.train`;
   narrative in PROJECT.md sections; `kind` + `todo` in run.json; strict order; grid search in-process (D-4); budget
   shown, never enforced (D-6). The skill coordinates; it never does a specialist's work or writes Python.
2. *Running the ledger* — the one canonical snippet, from the repo root, used for every ledger change (shown once,
   referenced everywhere else):
   ```bash
   uv run --locked --project packages/datalab python -c "
   from pathlib import Path
   from datalab import ledger
   d = Path('projects/<name>')
   l = ledger.read(d)
   l = ledger.<op>(l, ...)          # produce / decide / freeze_split / record_data / redo
   ledger.write_atomic(d, l)
   "
   uv run --locked --project packages/datalab python -m datalab.ledger validate projects/<name>
   ```
   and its MLflow twin (`Project` + `Settings` built the same way for `project_spend`, `stale_runs`, `close_runs`):
   ```bash
   uv run --locked --project packages/datalab python -c "
   from datetime import timedelta
   from pathlib import Path
   from datalab import tracking
   from datalab.project import load
   from datalab.settings import Settings
   p, s = load(Path('projects/<name>')), Settings()
   print(tracking.project_spend(p, s))
   for r in tracking.stale_runs(p, s, timedelta(hours=24)): print(r)
   "
   ```
   `close_runs(p, s, ["<id>", ...])` replaces the last two lines **only after the expert named the ids** (F-9).
3. *Start or resume* — (a) `projects/<name>` must exist (else: run `datalab-new <name>`); (b) list stale RUNNING runs
   (> 24 h) with the MLflow snippet, show them, ask with AskUserQuestion which to close (none is a valid answer), then
   `close_runs` with exactly those ids; (c) no run.json → governance gate (section 4), ask the kind (training |
   comparison) and the metric; write the card `metric: {key, goal}` first, then `new_ledger(kind, "<key> (<goal>): <one
   line>")` + `write_atomic` + `validate` (V-3 ties the two); (d) run.json present → `validate`; exit 1 → quote it
   verbatim, never guess; a corrupt file → tell the expert, reconstruct from PROJECT.md + artifacts, write with
   `replace_corrupt=True` only after the expert agrees; (e) the current milestone `produced` with decision null or
   `correct` → re-present it and re-ask; never advance on the pointer alone.
4. *Governance* — non-public data (proprietary, personal, NDA/regulated) needs explicit sign-off (e.g. Bedrock with
   `CLAUDE_CODE_USE_BEDROCK=1`) before scoping; unknown status = non-public; public HF datasets proceed.
5. *The flow* — the kind's sequence read from `contracts/milestones.json` (never hardcoded); after `dataset` validated →
   acquire data (retry once on a network error; gated dataset without `HF_TOKEN` → stop "auth required"; never partial
   data) → freeze the split (section 7); before `modeling` → BOX ⏸️ (section 8); after `modeling` → Hydra gate (`python
   tools/pre_commit_checks/hydra_gate.py projects/<name>`); `audit` → fresh-context `ds-validator` (section 9).
6. *The ⏸️ protocol* (every milestone) — (1) dispatch the milestone's agent with its brief (`references/dispatch-briefs.md`)
   + the overrides block (`references/agent-overrides.md`); (2) `produce(l, m, artifacts)` → `write_atomic` → `validate`
   (exit ≠ 0 → stop and report); (3) append the narrative to PROJECT.md (Approche during work, Enseignements for
   findings); (4) present: a tight summary, artifact paths, **the metric restated**, and the milestone's past
   `decisions_log` notes; (5) STOP and ask with AskUserQuestion, options exactly `validate`, `correct`, `redo` (+ at the
   audit `redo modeling`); no answer, an ambiguous one or silence → ask again, never assume; (6) `decide(...)` with the
   expert's words as note → `write_atomic` → `validate`; (7) `correct` → re-dispatch with the correction, then `produce`
   again; `redo` → section 10; `validate` → next milestone. Card status: scoping validated → set `status: en cours`;
   report validated → `status: conclu`. Never two milestones without an explicit `validate` in between.
7. *Split freeze* — right after `dataset` is validated and BEFORE any other dispatch: write `projects/<name>/split.json`
   (comparison: `grouped`, group_key persona/question id, **train = dev, val may be empty, test non-empty**), `validate`,
   then `freeze_split(l, split_path, summary)`. Before the freeze only target/group_key/time_col may be read; after it
   EDA uses train+val; test is read by nobody until the audit, then only through `python -m <pkg>.eval` (U-24). Never
   recomputed.
8. *BOX* — before dispatching `ds-modeler`: `record_data(l, Path("projects/<name>/data/clean/data.jsonl"))` (the template's `paths.data_file`: the full data the card ranks on);
   present for validation the candidates (`configs/model/*.yaml` + the experiment's `candidates:`), the grid
   (`configs/hparams_search/<grid>.yaml`, one child per combination, the child count), any secondary metric keys
   (`experiment.metrics`), and — **display only** — the BOX budget next to `project_spend` (all `<project>/*`, all
   statuses). Nothing stops on the budget (D-6); the expert decides. No `--multirun` (D-4). The BOX is not a milestone.
9. *Audit and winner* — at the modeling ⏸️ the expert picks the winning child (leaderboard = FINISHED children of the
   modeling parent); `validate` = `decide(l, "modeling", VALIDATE, note, winner=Winner(<family>, <child run id>))`.
   The audit runs `uv run python -m <pkg>.eval` from the project dir (winner by default; a grid winner's params as the
   family then its keys, e.g. `uv run python -m <pkg>.eval model=<winner family> model.<k>=<v>` — eval's refusal prints
   that exact form; a bare `model.<k>=<v>` only parses when the family is `dummy`). Before any
   further eval call `test_access_problem`; when it asks for a note, get the expert's reason with AskUserQuestion and pass
   it as one quoted Hydra override, `"look_note='<reason>'"` (the inner quotes keep commas and spaces). Every look is
   recorded in run.json by eval itself.
10. *Redo and demotion* — `redo` of k: `decide(l, k, REDO, note)` resets k and later to `todo` (U-2) and clears the
    split/dataset/features/winner/data fields at or before their milestone; tell the expert which milestones were demoted
    and that their artifacts are stale. Audit `redo modeling` = `decide(l, "audit", REDO, note, redo_from="modeling")`;
    `correct` re-runs only the audit (a new look, so a note). A Hydra-gate FAIL after modeling counts as `redo` of modeling.
11. *Archive and restart* (U-17) — the kind is fixed once scoping is validated. To change it, or to start a new
    experiment after `report` is validated: move `run.json` to `run.<YYYY-MM-DD>.json` (never overwrite: `-2`, `-3`),
    then a new ledger at scoping.
12. *Tracking milestone* — list stale runs and ask again (section 3b), then `ds-mlflow-tracker`.
13. *Code changes* — specialists never edit `src/` or `tests/`; for code the skill writes a one-phase `/plan-features`
    plan (archive a live plan with `/plan-archive` first), runs `/implement-phase 1`, then `/check`; only a green `/check`
    lets the milestone be `produced`. YAML under `configs/` and Markdown artifacts may be written by specialists.
14. *Rules recap* — metric restated everywhere; kind immutable; pre-freeze reads; test only through the gated eval;
    budget shown, not enforced; stale runs closed only on the expert's word; governance; no credentials in configs,
    ledger, MLflow or artifacts; resume from disk, not from the conversation.
**Constraints:** ≤ 250 lines; every ledger change via the section-2 snippet (never hand-edited JSON); ids and order from
`contracts/milestones.json`. **Reference:** `~/.claude/skills/trouvetou/SKILL.md:65-221`.

### `.claude/skills/experiment/references/dispatch-briefs.md` (new)
One brief per milestone (all 9 ids of `contracts/milestones.json`): heading = id + `subagent_type`; fields `Inputs`
(`projects/<name>/PROJECT.md`, `scope.md`, `split.json` from the freeze on, prior artifacts), `Metric` (literal
`{metric}` placeholder, always present), `Deliverable` (paths under `projects/<name>/`: `scope.md`, `dataset.md`,
`eda.md`, `audit.md`, `tracking.md`, `reports/report.html`), `Allowed reads` (scoping/dataset: target/group_key/time_col
only; cleaning/eda/features/modeling: train+val; audit: test through `python -m <pkg>.eval` only), `Forbidden` (editing
`src/`/`tests/`, recomputing the split, a URI in config, `--multirun`, a metric key carrying a candidate name), `Return`
(the agent's output structure from its `ds-*.md`). Cleaning adds "keep the row count and order of the file `split.json` indexes; a drop is a post-split filter".
Modeling adds the validated BOX (candidates, grid, child count,
displayed budget) and `python -m <pkg>.train experiment=<name> hparams_search=<grid>`; audit adds the winner (family +
run id + params), the leaderboard, `split.json`, `scope.md`, "fresh context, try to break the winner", and the look rule.

### `.claude/skills/experiment/references/agent-overrides.md` (new)
**Common block** (pasted into every dispatch): MLflow URI only from `DATALAB_MLFLOW_TRACKING_URI` (shared 5050, D-1);
experiment `<project>/<experiment.name>`, eval in `<project>/audit`; one parent per invocation, one child per grid
combination (`<family>-<i>`, tag `candidate`), only children log `metric.key` and `cost_usd`, no candidate name in a
metric key; every paid call inside a `tracked_trial`; `projects/<name>/` (uv env, `python -m <pkg>.train`); narrative in
PROJECT.md; budget shown at the BOX only; no credentials anywhere.
**Per-agent table** (agent · trouvetou behaviour (cite line) · data-lab override):
`ds-mlflow-tracker` (`ds-mlflow-tracker.md:18`, `tracking_uri` from `configs/logger/mlflow.yaml`, default sqlite) → no
`logger/` group exists; URI from the env var, never a local `mlruns/`; verify, do not re-log trials ·
`ds-validator` (`ds-validator.md:18`, re-scores the frozen test itself) → only `python -m <pkg>.eval`, which the ledger
gates; a second look needs the expert's `look_note`; results in `audit.md` ·
`ds-modeler` (`ds-modeler.md:25`, logs every trial its own way, runs its own bounded search) → trials are children made
by `train.py`; it edits `configs/model/*`, `configs/experiment/*`, `configs/hparams_search/*` (grid lists only), never
enforces a budget, asks for code through the plan route · `ds-data-cleaner`/`ds-feature-engineer` (pipeline code in
`src/<project>/…`) → a code spec routed through `/implement-phase` + `/check` · `ds-data-cleaner` (`ds-data-cleaner.md:42`,
documents dropped rows) → `data/clean/data.jsonl` keeps the row count and order of the file the split indexes; a drop is a
filter column/flag applied after partitioning, never a removed line (the loader refuses a split that does not cover the rows) · `ds-reporter` (`ds-reporter.md:27`,
reads `project.md`) → reads PROJECT.md + run.json, writes `projects/<name>/reports/report.html` · all agents (trouvetou
`SKILL.md:36-63` Step 0) → nothing is copied into the project.

## Dry-run walkthrough checklist (the acceptance)
Setup: `uv run --project packages/datalab datalab-new exp-dryrun`, then walk the skill text milestone by milestone
(simulated agent outputs are fine). **Teardown (always, pass or fail):** `rm -rf projects/exp-dryrun` and
`git restore .pre-commit-config.yaml .github/workflows/ci.yml` (reverts the wiring `datalab-new` wrote); `git status`
shows neither. One failed check = phase not done.

| # | Check | Expected |
|---|-------|----------|
| 1 | Start without run.json | governance, kind + metric asked; card metric written; `new_ledger` written; `validate` 0 |
| 2 | Every milestone | a ⏸️ with exactly validate/correct/redo; past notes shown; no dispatch before an explicit answer |
| 3 | Every brief and presentation | the restated metric (`{metric}` in all 9 briefs) |
| 4 | Ledger writes | only via the section-2 snippet, each followed by `validate` |
| 5 | Split | frozen right after dataset validated, before any other dispatch; comparison val may be empty |
| 6 | Pre-freeze reads / test isolation | scoping/dataset briefs: target/group_key/time_col only; no brief before audit names `eval` or test |
| 7 | BOX | `record_data` called; candidates, grid, child count, budget **and** `project_spend` shown; no stop on budget |
| 8 | Hydra gate | run after modeling, before audit; FAIL → redo modeling |
| 9 | Winner | modeling `validate` carries `winner=Winner(...)`; audit eval uses it |
| 10 | Second look | a 2nd eval asks the expert for a note and passes `look_note` |
| 11 | Audit redo | `redo modeling` → `decide(.., "audit", REDO, .., redo_from="modeling")` → modeling + audit `todo` |
| 12 | Demotion | redo of `eda` on a training ledger → eda…report `todo`, expert told which |
| 13 | Kind change / new experiment | run.json archived as `run.<date>.json`; new ledger; never an in-place kind edit |
| 14 | Stale runs | listed at resume and before tracking; closed only with the ids the expert named |
| 15 | Card status | `en cours` after scoping validated, `conclu` after report validated |
| 16 | Code / corrupt run.json | no specialist edits `src/`; corrupt file quoted, `replace_corrupt=True` only after agreement |
| 17 | Overrides / sequence | each row above is in `agent-overrides.md` with its citation; ids read from `milestones.json` |
| 18 | Teardown | `projects/exp-dryrun` gone, both config files back to `HEAD` |
| 19 | Split ↔ clean rows | cleaning brief and `ds-data-cleaner` override: same row count and order as the indexed file, drops as a post-split filter |

<!-- plan-validate: READY 2026-11-06 sha256:bcc3408ca4b1 -->
