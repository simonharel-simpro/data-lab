---
name: experiment
description: Run a data-lab experiment milestone by milestone with the ds-* specialists, stopping for expert validation at each step (projects/<name>, run.json ledger, frozen split, shared MLflow).
---

# /datalab:experiment — the data-lab orchestrator

**Working directory.** Every command runs from the workspace root (the folder holding `datalab.toml`);
`projects/<name>` paths are relative to it. "Inside data-lab" means the workspace root holds `packages/datalab/` **and**
`compose.yaml` (the same predicate as `datalab.project.is_datalab_checkout`); a step marked inside data-lab is the
only thing that differs in another workspace.

**Agents.** The `ds-*` specialists come from the user-level trouvetou install (#47); this plugin ships none.

## 1. What this is

An adaptation of trouvetou (`~/.claude/skills/trouvetou/SKILL.md`) to data-lab. You coordinate the ds-* specialists
(Agent tool, `subagent_type` = the agent's name), present their work, and STOP for the expert at every milestone. You
never do a specialist's work and you never write Python: code goes through section 13.

| trouvetou | data-lab |
|-----------|----------|
| per-project `sqlite:///mlflow.db` | the shared MLflow server, URI only from `DATALAB_MLFLOW_TRACKING_URI` (D-1) |
| Step 0 copies `assets/` into the project (`SKILL.md:36-63`) | no Step 0: `datalab-new` already scaffolded everything |
| `runs/<name>/`, `requirements.txt`, `python -m src.<p>.train` | `projects/<name>/`, uv env, `python -m <pkg>.train` (`<pkg>` = name with `-` → `_`) |
| `project.md` narrative | sections of `PROJECT.md` (Approche, Enseignements, Suite) |
| `run.json` without kind or todo | `run.json` with `kind` (training \| comparison \| exploration) and `todo` statuses, strict order |
| `--multirun` sweeps, budget a hard stop | grid in-process, one child per combination (D-4); budget shown, never enforced (D-6) |

Contracts: `EXPERIMENT.md` (the experiment contract) and `milestones.json` (milestone ids, agents and sequences: the
only source for them). Read each at the path printed by
`uv run --project projects/<name> python -m datalab.resources EXPERIMENT.md` (resp.
`uv run --project projects/<name> python -m datalab.resources milestones.json`). If that command fails with
`No module named datalab.resources`, stop and tell the expert to run `uv lock --upgrade-package datalab` in
`projects/<name>`. Before the project exists, the contract read waits until after `datalab-new`.

## 2. Running the ledger

Every ledger change uses this snippet, from the workspace root; never hand-edit `run.json`. Python strings are
triple-quoted so the expert's words pass verbatim; the quoted heredoc stops the shell from expanding them.

```bash
uv run --locked --project projects/<name> python - <<'PY'
from pathlib import Path
from datalab import ledger
d = Path('projects/<name>')
l = ledger.read(d)
l = ledger.<op>(l, ...)          # produce / decide / freeze_split / record_data / redo
ledger.write_atomic(d, l)
PY
uv run --locked --project projects/<name> python -m datalab.ledger validate projects/<name>
```

- The first ledger: replace the `read` and `<op>` lines with `l = ledger.new_ledger(ledger.Kind.TRAINING, """...""")`
  (or `Kind.COMPARISON` / `Kind.EXPLORATION`).
- A decision: `ledger.decide(l, "<m>", ledger.Decision.VALIDATE, """<expert's words>""")`; modeling adds
  `winner=ledger.Winner(candidate="<family>", run_id="<child run id>")` (keywords only).
- The `dataset` and `features` fields (no op sets them): add `import json`, then
  `l = ledger.parse(json.dumps(l.model_dump(mode="json") | {"dataset": {"id": "<hf id>", "hash": "<revision sha>"}}))`
  (`{"features": [...]}` the same way, training only). `parse` re-checks every invariant.
- Read-only questions use the same body without `write_atomic` (e.g. `print(ledger.test_access_problem(...))`).

The MLflow twin (the tracking functions take the project **name**):

```bash
uv run --locked --project projects/<name> python - <<'PY'
from datetime import timedelta
from pathlib import Path
from datalab import tracking
from datalab.project import load
from datalab.settings import Settings
p, s = load(Path('projects/<name>')), Settings()
print(tracking.project_spend(p.name, s))
for r in tracking.stale_runs(p.name, s, timedelta(hours=24)): print(r)
PY
```

`print(tracking.close_runs(p.name, s, ["<id>", ...]))` replaces the last two lines **only after the expert named the
ids** (F-9).

## 3. Start or resume

Always resume from disk, never from the conversation.

a. `projects/<name>/` must exist; else tell the expert to create it from the workspace root — see README §New project
   (inside data-lab: `uv run --project packages/datalab datalab-new <name>`; another workspace: the `uvx` bootstrap).
b. Stale runs: run the MLflow twin, show every stale RUNNING run (> 24 h), ask with AskUserQuestion which to close
   ("none" is a valid answer), then `close_runs` with exactly those ids. Never close a run the expert did not name.
c. No `run.json`: governance gate (section 4); ask the kind (training | comparison | exploration) and the metric
   (key + goal `max`/`min` + one line). Pick exploration to look at data, try an architecture or benchmark without
   a frozen test; it states what it looks at as its metric line. Write the card `metric: {key, goal}` in `PROJECT.md` first, then `new_ledger(kind,
   "<key> (<goal>): <one line>")` + `write_atomic` + `validate` (V-3 ties the two).
d. `run.json` present: `validate`. Exit 1: quote the FAIL line verbatim and never guess a fix. A corrupt file (invalid
   JSON, schema, `kind missing`): tell the expert, reconstruct from `PROJECT.md` + the artifacts on disk, show the
   reconstruction, and write it with `write_atomic(d, l, replace_corrupt=True)` only after the expert agrees.
e. The current milestone `produced` with decision null or `correct`: re-present it (section 6, step 4) and re-ask.
   Never advance on `current_milestone` alone.

## 4. Governance

Non-public data (proprietary, personal, NDA or regulated) needs the expert's explicit sign-off before scoping, e.g.
running Claude Code through Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`). Unknown status = non-public: ask. Public Hugging
Face datasets proceed without sign-off.

## 5. The flow

Read the kind's sequence from `milestones.json` (section 1; `sequences.<kind>`, agent per id in `milestones`); never
hardcode it. Run each milestone with the ⏸️ protocol (section 6). A transition whose milestone is absent from the
sequence never runs; an exploration logs runs (if any) from project code with
`datalab.tracking`. Transition work, which is not a milestone:

- After `dataset` is validated: acquire the data exactly as `dataset.md` names it (id + revision). Write the rows as
  JSONL to `data/raw/data.jsonl`; a kind whose sequence has no `cleaning` milestone also copies it unchanged to
  `data/clean/data.jsonl` (`paths.data_file`). A network error: retry once, then stop and report. A gated dataset
  without `HF_TOKEN`: stop, "auth required". A size beyond the disk or the run: ask first. Never proceed on partial
  data, never fabricate. Then freeze the split (section 7) before any other dispatch.
- Before `modeling`: the BOX (section 8).
- After `modeling` is produced: the Hydra gate. Inside data-lab: `python3 tools/pre_commit_checks/hydra_gate.py
  projects/<name>` (mandatory; a missing script is an error); FAIL = a redo of modeling (section 10); do not present
  the winner. In another workspace: skip it and say `no Hydra gate outside data-lab (#48)`.
- `audit`: fresh-context `ds-validator` (section 9).
- `tracking`: list stale runs and ask again (section 3b) before dispatching `ds-mlflow-tracker`.

## 6. The ⏸️ protocol (every milestone)

1. Dispatch the milestone's agent with its brief (`references/dispatch-briefs.md`, `{metric}` = `run.json` `metric`)
   and the common block plus its row from `references/agent-overrides.md`. Pass artifacts by path.
2. `produce(l, "<m>", [<artifact paths relative to the project>])` → `write_atomic` → `validate`. Exit ≠ 0: stop
   and report the output.
3. Append the narrative to `PROJECT.md`: Approche while the work happens, Enseignements for findings.
4. Present: a tight summary, the artifact paths, **the metric restated** (`run.json` `metric`), and every past
   `decisions_log` note of this milestone.
5. STOP. Ask with AskUserQuestion, options exactly `validate`, `correct`, `redo` (at the audit add `redo modeling`).
   No answer, an ambiguous one or silence: ask again. Never assume.
6. `decide(l, "<m>", <Decision>, """<the expert's words>""")` → `write_atomic` → `validate`. Set `dataset` before
   validating `dataset` (I-11) and `features` before validating `features` (section 2).
7. `correct`: re-dispatch the same agent with the correction, then `produce` again and go back to step 3. `redo`:
   section 10. `validate`: the next milestone.

Card `status:` in `PROJECT.md`: scoping validated → `en cours`; report validated → `conclu`. Never two milestones
without an explicit `validate` in between; never dispatch the next agent "to save time".

## 7. Split freeze

Right after `dataset` is validated (and the data acquired), BEFORE any other dispatch:

1. Write `projects/<name>/split.json` (schema: `EXPERIMENT.md` §3 read through section 1, `datalab.split`) with the
   strategy, seed, target, group_key and time_col that `dataset.md` proposed and the expert validated. Index lists
   address the rows of the acquired file; their union is every row. A comparison: `grouped`, group_key the persona or question id,
   **train = the dev set, val may be empty, test non-empty**.
2. `validate`, then `freeze_split(l, d / "split.json", "<strategy, seed, partition sizes>")` → `write_atomic` →
   `validate`.

Reads: before the freeze only the target, group_key and time_col columns may be read; after it EDA and every later
milestone use train + val; test is read by nobody until the audit, then only through `python -m <pkg>.eval` (U-24).
The split is never recomputed; only a redo at or before `dataset` reopens it.

## 8. BOX (before dispatching `ds-modeler`; not a milestone)

1. `record_data(l, d / "data/clean/data.jsonl")` (the template's `paths.data_file`: the full data the card ranks
   on) → `write_atomic` → `validate`. The file must not change afterwards: train and eval check its hash.
2. Present for validation: the candidates (`configs/model/*.yaml` and the experiment's `candidates:`), the grid
   (`configs/hparams_search/<grid>.yaml`, one child per combination, the child count), the secondary metric keys
   (`experiment.metrics`), and — **display only** — the BOX budget next to `project_spend` (every `<project>/*`
   experiment, every status, RUNNING included).
3. Nothing stops on the budget (D-6): the expert decides. No `--multirun` (D-4). Ask validate / correct; dispatch
   `ds-modeler` only after an explicit validate of the BOX.

## 9. Audit and winner

- At the modeling ⏸️ the expert picks the winning child; the leaderboard is the FINISHED children of the modeling
  parent run (status ≠ FINISHED counted separately). `validate` = `decide(l, "modeling", ledger.Decision.VALIDATE,
  """<note>""", winner=ledger.Winner(candidate="<family>", run_id="<child run id>"))`.
- The audit dispatches `ds-validator` in a fresh context. Every eval runs from the project dir:
  `cd projects/<name> && uv run python -m <pkg>.eval` (the winner by default). A grid winner passes its family then
  its keys: `uv run python -m <pkg>.eval model=<winner family> model.<k>=<v>`; eval's refusal prints those overrides.
  A bare `model.<k>=<v>` only parses when the family is `dummy`.
- Before every eval call, ask the ledger: `print(ledger.test_access_problem(l, ledger.split_sha256(d / "split.json"),
  None))`. `None` = go. "needs an expert note": get the expert's reason with AskUserQuestion and pass it as one
  quoted Hydra override, `"look_note='<reason>'"` (the inner quotes keep commas and spaces). Any other answer: stop
  and report it. Eval records every look in `run.json` itself.

## 10. Redo and demotion

- `redo` of milestone k: `decide(l, k, ledger.Decision.REDO, """<note>""")`. It resets k and every later milestone to
  `todo` (U-2) and clears the split/dataset/features/winner/data fields whose milestone is k or later. Tell the expert
  which milestones were demoted (k to the end of the sequence) and that their artifacts are stale; then re-dispatch k.
- Audit `redo modeling`: `decide(l, "audit", ledger.Decision.REDO, """<note>""", redo_from="modeling")` → modeling and
  audit (and later) `todo`; the BOX runs again, `record_data` included. Audit `correct` re-runs only the audit: a new
  look, so a `look_note`.
- A Hydra-gate FAIL after modeling counts as a `redo` of modeling: show the FAIL output, record it as the note.

## 11. Archive and restart (U-17)

The kind is fixed once scoping is validated. To change it, or to start a new experiment after `report` is validated:
move `run.json` to `run.<YYYY-MM-DD>.json` (never overwrite: `run.<YYYY-MM-DD>-2.json`, `-3`, ...;
`mv -n` and check), then a new ledger at scoping (section 3c). Never edit `kind` in place.
Also move a present `split.json` to `split.<same suffix>.json` (decided 2026-11-07, ESC-4-1), so the archived
ledger keeps its frozen split and the new experiment re-freezes its own. If the same data is re-split, warn the
expert of possible test-row overlap: a new split over the same rows does not hide the old test rows, which have
been looked at.

## 12. Tracking milestone

List stale runs and ask again (section 3b), then dispatch `ds-mlflow-tracker` (verify, never re-log).

## 13. Code changes

Specialists never edit `src/` or `tests/`. When a milestone needs code: archive a live plan with `/plan-archive`,
write a one-phase `/plan-features` plan from the specialist's code spec, run `/implement-phase 1`, then `/check`. Only
a green `/check` lets the milestone be `produced`. Specialists may write YAML under `configs/` and Markdown artifacts.

## 14. Rules recap

- The metric is restated in every brief and every presentation; raise a reason it is wrong, never optimize around it.
- The kind is immutable after scoping: archive, never edit.
- Before the freeze: target/group_key/time_col only. Test: only through the gated `python -m <pkg>.eval`.
- Budget shown, not enforced. Stale runs closed only with the ids the expert named.
- Governance sign-off before non-public data.
- No credentials in configs, the ledger, MLflow or artifacts; no URI in a config.
- Every ledger change via section 2, each followed by `validate`. Resume from disk, not from the conversation.
