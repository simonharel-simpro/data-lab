# data-lab

A local, single-user data-science lab. One shared infra stack runs on your machine (Weaviate for vectors, MLflow for
experiment tracking). Many small projects plug into it, each in its own Python env. A read-only site tells each
project's story: what it tried, its best run, what was learned.

The point: a new idea starts in one command, with the same conventions every time (settings, naming, tracking, a
project card). You don't rebuild the plumbing per experiment, and finished work stays readable afterwards.

## Contents

- [How it fits together](#how-it-fits-together)
- [Quickstart](#quickstart)
- [Typical workflow](#typical-workflow)
- [How Claude runs an experiment](#how-claude-runs-an-experiment)
- Reference: [Prerequisites](#prerequisites) · [Clone](#clone) · [Shared infra](#shared-infra) ·
  [Weavit UI](#weavit-ui) · [New project](#new-project) · [App](#app) · [Pilot](#pilot) ·
  [Claude Code](#claude-code) · [Checks](#checks)
- [Further reading](#further-reading)

## How it fits together

```
  projects/<name>/                      shared stack (docker compose, 127.0.0.1 only)
  ├─ PROJECT.md   (the card)            ┌──────────────────────────────┐
  ├─ configs/     (Hydra)   ─datalab──► │ MLflow    :5050  runs        │ ◄── app/  Astro site, read-only
  └─ src/<pkg>/   train/eval   package  │ Weaviate  :8090  collections │ ◄── Weavit UI  :3080
                                        └──────────────────────────────┘
```

| Piece | Where | Role |
|---|---|---|
| Shared stack | `compose.yaml` | Weaviate + English vectorizer (bge-small), MLflow; LiveKit under the `voice` profile |
| `datalab` package | `packages/datalab/` | settings (`DATALAB_*`), project naming, `tracked_run()`, the experiment ledger, the `datalab-new` scaffolder |
| Projects | `projects/<name>/` | one uv env each, a `PROJECT.md` card, Hydra `train`/`eval` from the template |
| App | `app/` | one page per project: its card plus its best MLflow run; never writes anything |
| Weavit UI | `tools/weavit-ui/` (submodule) | browse and query the shared Weaviate, in the browser or as a desktop app |
| Claude plugin | `plugins/datalab/` | `/datalab:experiment`: runs an experiment milestone by milestone with the `ds-*` agents |
| Contracts | `contracts/` | the rules shared by the Python side and the app (`EXPERIMENT.md`, milestones, tags) |

Current projects: `mini-rag`, the end-to-end pilot (BM25 vs vector retrieval plus an LLM, see [Pilot](#pilot)), and
`voice-arch`, which compares voice-agent architectures on LiveKit (see `projects/voice-arch/README.md`).

## Quickstart

You need Docker, uv and Node 22 (details in [Prerequisites](#prerequisites)). Then, in about ten minutes:

```bash
git clone --recurse-submodules https://github.com/simonharel-simpro/data-lab.git && cd data-lab
cp .env.example .env                  # the defaults work; add OPENROUTER_API_KEY only if you need it
docker compose up -d && docker compose ps     # wait until all three services are "healthy"

# run the pilot (needs an OpenRouter key)
cd projects/mini-rag && uv sync
echo 'MINI_RAG_LLM_API_KEY=<openrouter-key>' > .env
uv run python -m mini_rag.run --retrieval bm25 --k 3

# look at the result
cd ../../app && nvm use && npm ci && npm run dev   # http://127.0.0.1:4321, the mini-rag card
```

MLflow's own UI is at http://127.0.0.1:5050, and `tools/weavit-web.sh` opens the Weaviate browser at
http://127.0.0.1:3080.

## Typical workflow

1. **Start a project.** `uv run --project packages/datalab datalab-new my-idea --title "My idea"`, then
   `cd projects/my-idea && uv sync`. You get a card, a Hydra layout and an env wired to the shared stack
   ([New project](#new-project)).
2. **Write the card.** Fill `## Objectif` in `PROJECT.md` (status `idée`). The app shows a "À compléter" badge for
   whatever the current status still requires.
3. **Run the experiment.** There are two ways:
   - with Claude Code: `/datalab:experiment` runs the milestones in order, from scoping to report, and stops for
     your validation at each one. Which milestones depends on the experiment kind (`training`, `comparison` or
     `exploration`, see `contracts/milestones.json`). See [How Claude runs an experiment](#how-claude-runs-an-experiment).
   - by hand: put candidates in `configs/model/`, then `uv run python -m my_idea.train experiment=default`, then
     `uv run python -m my_idea.eval`. Each run lands in MLflow tagged `project=my-idea`.

   Set `status: en cours` and add `## Approche`, `data` and `metric` to the card. The `metric` field is what picks the
   best run shown in the app.
4. **Look.** Check the project page in the app, the runs in MLflow, and the collections in Weavit.
5. **Close it.** Set `status: conclu` (or `abandonné`) and fill `## Enseignements` and `## Suite`. For something you
   want to show, `DATALAB_STRICT_EXPORT=1 npm run build` in `app/` freezes it as a static site.

## How Claude runs an experiment

`/datalab:experiment` (in `plugins/datalab/`) is an orchestrator. It does none of the data-science work itself: it hands
each step to a specialist `ds-*` agent, shows you the result, and **stops until you decide**. Everything it does is
recorded in a ledger, `projects/<name>/run.json`, so a session can stop at any point and resume from disk.

**1. Start.** Run the skill from the workspace root and name the project. If `run.json` is missing, it asks two
things: the experiment **kind** and the **metric** (`key`, `goal`, one line on why). It writes the metric to the
card and creates the ledger. Non-public data (proprietary, personal, regulated) needs your explicit sign-off first;
public Hugging Face datasets don't.

**2. Milestones.** The kind sets the sequence (`contracts/milestones.json`). Each milestone has one agent:

| Milestone | Agent | training | comparison | exploration |
|---|---|:-:|:-:|:-:|
| scoping | `ds-scoper` | ✓ | ✓ | ✓ |
| dataset | `ds-dataset-finder` | ✓ | ✓ | |
| cleaning | `ds-data-cleaner` | ✓ | | |
| eda | `ds-eda` | ✓ | ✓ | ✓ |
| features | `ds-feature-engineer` | ✓ | | |
| modeling | `ds-modeler` | ✓ | ✓ | |
| audit | `ds-validator` | ✓ | ✓ | |
| tracking | `ds-mlflow-tracker` | ✓ | ✓ | |
| report | `ds-reporter` | ✓ | ✓ | ✓ |

**3. The ⏸️ stop, at every milestone.** The agent produces its artifacts, which are recorded in the ledger. Claude
then shows a short summary, the artifact paths and the metric restated, and asks you: **validate**, **correct**
(same milestone, with your feedback) or **redo**. A redo resets that milestone and every later one to `todo`. At the
audit you can also send it back to modeling. Two milestones never run without a validate in between.

**4. Guards along the way.**

- **Frozen split.** Right after `dataset` is validated, the data is downloaded as named (id + revision) and the
  train/test split is frozen in `split.json`. Before that, only the target, group and time columns may be read.
- **BOX before modeling.** Claude pins the data file's hash, then shows the candidates (`configs/model/`), the
  search grid with its run count, and the budget next to what the project has already spent. Modeling starts only
  after you validate. The budget is shown, never enforced: you decide.
- **Winner and audit.** At modeling you pick the winning run from the MLflow leaderboard. The audit runs
  `ds-validator` in a fresh context to try to break that winner (leakage, overfitting, a gamed metric). It is the
  only step that reads the test partition, through the gated `python -m <pkg>.eval`, and every look at the test set
  is logged in `run.json`.
- **Code goes through the harness.** Specialists only write `configs/` YAML and Markdown. When a milestone needs code
  in `src/`, Claude writes a plan (`/plan-features`), implements it (`/implement-phase`) and runs `/check`. The
  milestone only counts as produced once the check passes.

**5. Card and finish.** Validating scoping sets the card to `en cours`, and validating report sets it to `conclu`.
The kind can't change after scoping: to change it, or to start a new experiment on the same project, Claude archives
`run.json` and `split.json` as `run.<date>.json` and `split.<date>.json` and starts a new ledger.

The full rules are in `plugins/datalab/skills/experiment/SKILL.md`, and the contract it enforces is
`contracts/EXPERIMENT.md`. Setup (installing the plugin and the `ds-*` agents) is in [Claude Code](#claude-code).

The rest of this file is reference.

## Prerequisites

- Docker (with the `docker compose` plugin)
- [uv](https://docs.astral.sh/uv/) for Python
- Node 22 via nvm (`nvm use` reads `.nvmrc`)
- Keep the repo on the Linux filesystem (e.g. `~/projects/...`), not under `/mnt/c`: bind mounts, file watching
  and `uv`/`npm` installs are much slower and less reliable across the WSL boundary.

## Clone

```bash
git clone --recurse-submodules https://github.com/simonharel-simpro/data-lab.git
cd data-lab
git config push.recurseSubmodules check   # refuse to push a superproject that points at an unpushed fork commit
```

Already cloned without `--recurse-submodules`? Run `git submodule update --init`.

## Shared infra

```bash
docker compose up -d     # start Weaviate, the vectorizer and MLflow
docker compose ps        # all three should become "healthy" (the vectorizer takes ~30 s)
docker compose down      # stop; data is kept in named volumes
```

> **Warning:** `docker compose down -v` deletes the named volumes, i.e. the Weaviate collections and MLflow
> runs of **every** project. There is no undo.

Every port is bound to `127.0.0.1` only: the services are unauthenticated (auth deferred, #2).

| Service | Host address | Container port | Env var (`.env.example`) |
|---|---|---|---|
| MLflow | `http://127.0.0.1:5050` | 5000 | `DATALAB_MLFLOW_TRACKING_URI` |
| Weaviate REST | `127.0.0.1:8090` | 8080 | `DATALAB_WEAVIATE_HTTP_PORT` |
| Weaviate gRPC | `127.0.0.1:50052` | 50051 | `DATALAB_WEAVIATE_GRPC_PORT` |
| text2vec-transformers | not published | 8080 | — |

Why not 5000 / 8080 / 50051: the Demo-RAG stack already uses them and keeps running side by side (D-4). The
`DATALAB_` prefix keeps a stray `MLFLOW_TRACKING_URI` from sending runs to Demo-RAG.

## Weavit UI

The fork lives in `tools/weavit-ui`. It runs **in the browser** (web mode) or as the desktop app.

```bash
tools/weavit-web.sh              # http://127.0.0.1:3080 — node >= 22; builds on first run
tools/weavit-web.sh --rebuild    # after updating the submodule
```

Web mode creates the `data-lab` profile itself and auto-connects. In dev, each project page links its best run's
collection ("Ouvrir dans Weavit", via the run's `collection` param; `DATALAB_WEAVIT_URL` overrides the address).
The RAG tab's **OpenRouter (deepseek-v4-flash)** preset uses `OPENROUTER_API_KEY` from the root `.env`: the
launcher hands it to the local server, which keeps it in memory and sends it to Weaviate only as the
`X-OpenAI-Api-Key` header. The server listens on 127.0.0.1 only and refuses foreign `Host`/`Origin` headers: it can
delete collections.

Desktop app: build and run it as described in [its README](tools/weavit-ui/README.md), and create once a
**local** connection profile named exactly **`data-lab`** with **HTTP port 8090 AND gRPC port
50052**, both filled in explicitly. An empty gRPC field falls back to 50051 — Demo-RAG's Weaviate — and you get a
split-brain view: REST on data-lab, gRPC on Demo-RAG (F-4).

## New project

Inside data-lab (use the editable command, not `uvx`: the project then depends on `packages/datalab` by path):

```bash
uv run --project packages/datalab datalab-new mini-rag --title "Mini RAG"   # from the repo root
cd projects/mini-rag && uv sync
```

In another repo (a workspace): mark its root with `datalab.toml`, then bootstrap from git.

```bash
touch datalab.toml
uvx --refresh --from "git+https://github.com/simonharel-simpro/data-lab#subdirectory=packages/datalab" datalab-new mini-rag
cd projects/mini-rag && uv sync
```

This needs read access to the private repo and git credentials (`gh auth setup-git`). It creates `projects/` and a
`ruff.toml` in the workspace (an existing one is kept), and writes no hook/CI wiring there yet (#48). The project
depends on datalab through `branch = "main"`, and its `uv.lock` pins the commit; get a newer datalab with
`uv lock --upgrade-package datalab` in the project. Project names are unique per stack: every workspace logs to the
same local MLflow (a clash warning is tracked in #50). To see a workspace's projects in the app, run it with
`DATALAB_PROJECTS_DIR=<ws>/projects` (ledgers written by a datalab at another commit may not render).

Naming rules: lowercase letters and digits, single dashes between words (`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`), not a
reserved word (`test`, `datalab`, `datalab-test`, `template`, and the YAML words `y n yes no on off true false
null`). An existing `projects/<name>` (even an empty folder or a file) is refused and nothing is written.

The template (`templates/project/`) gives: `PROJECT.md` (the card: `name`, `title`, `status: idée`, `tags`, four
sections to fill), a `pyproject.toml` named `proj-<name>` that depends on datalab (editable path dep inside
data-lab, git dep elsewhere), an empty `src/` for your package, `.env.example` and a short README.

In code: `datalab.project.load()` (identity from `PROJECT.md`), `datalab.project.collection_name()` (Weaviate),
`datalab.tracking.tracked_run()` (MLflow run tagged `project=<name>`), `datalab.settings.Settings` (`DATALAB_*`).

## App

A read-only Astro site (`app/`): one page per `projects/<name>/PROJECT.md`, with the project's best MLflow run
(the card's `metric {key, goal}`, among FINISHED runs tagged exactly `project=<name>`). It never writes anything.

```bash
cd app && nvm use && npm ci
npm run dev                          # local live mode: http://127.0.0.1:4321, cards and metrics re-read per request
DATALAB_STRICT_EXPORT=1 npm run build   # showable static export in app/dist/ (fails if MLflow is down)
npm run check && npm test            # astro check + unit tests (line coverage floor 70 %)
```

- **Two modes.** `npm run dev` links run names to MLflow and shows the MLflow URI in the footer. `npm run build`
  freezes the metrics at build time and contains no link to `127.0.0.1` (D-14). Without `DATALAB_STRICT_EXPORT=1`
  a build with MLflow down still succeeds and shows "Métriques indisponibles" on cards with a metric (that is what
  CI does); use the strict flag for any export you show. Note: `astro dev` detaches from a non-interactive shell and
  prints its own PID; stop it with `astro dev stop` (from `app/`) or Ctrl-C in a terminal.
- **MLflow URI:** `DATALAB_MLFLOW_TRACKING_URI` (default `http://127.0.0.1:5050`); `MLFLOW_TRACKING_URI` is ignored.
- **Badge "À compléter : …"** lists what the card still lacks for its status: `idée` needs `## Objectif`;
  `en cours` adds `## Approche`, `data` and `metric`; `conclu`/`abandonné` add `## Enseignements` and `## Suite`.
  A section with only an HTML comment (as in the template) counts as empty.
- **Invalid cards fail the build** with the file named (D-13): unknown `status`, a `name` that breaks the naming
  rules or differs from its folder, a `metric.key` with characters outside `A-Z a-z 0-9 _ . - /`.

## Pilot

`projects/mini-rag` is the end-to-end example (BM25 and vector retrieval over a frozen snapshot of these docs,
answers from an LLM, OpenRouter by default). With the stack up (`docker compose up -d`):

```bash
cd projects/mini-rag && uv sync
echo 'MINI_RAG_LLM_API_KEY=<openrouter-key>' > .env          # gitignored; required (DGX: see .env.example)
for r in bm25 vector; do for k in 3 5; do uv run python -m mini_rag.run --retrieval $r --k $k; done; done
cd ../../app && npm run dev                                   # the mini-rag card: best `score` of the 4 runs
```

The runs land in MLflow under `mini-rag/retrieval` (tag `project=mini-rag`), the chunks in a Weaviate collection
prefixed `MiniRag_`. `--n N` runs the first N questions only: it logs `smoke_*` metrics and tag `smoke=true`, never
`score`, so a smoke run never becomes the card's best run (D-15). A perfect run scores 0.9: 2 of the 20 questions
are unanswerable and "I don't know" counts as missing (D-7).

## Claude Code

The `/datalab:experiment` skill (runs a project's experiment milestone by milestone, contract
`contracts/EXPERIMENT.md`) ships in the `datalab` plugin (`plugins/datalab/`), served by the `data-lab` marketplace at
this repo's root (`.claude-plugin/marketplace.json`). Install it once, for any workspace:

```bash
claude plugin marketplace add simonharel-simpro/data-lab
claude plugin install datalab@data-lab
claude plugin marketplace update data-lab      # later: pull the skill from the latest main
```

This needs read access to the private repo and git credentials (`gh auth setup-git`). After a plugin update, run
`uv lock --upgrade-package datalab` in each project so its contracts match the skill (U-12). The skill dispatches the
`ds-*` agents, which the plugin does not ship: install them separately at user level via trouvetou (#47).

In data-lab, test unpushed skill edits with `claude --plugin-dir plugins/datalab` (disable the installed copy with
`claude plugin disable datalab@data-lab` if both load). `.claude/hooks/` holds the loop guards and the statusline meter.

## Checks

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
pre-commit run --all-files
uvx pytest tests/        # compose port contract (needs docker on PATH)
(cd packages/datalab && uv run pytest --cov=datalab)   # unit tests, coverage >= 70 %
(cd packages/datalab && uv run pytest -m integration)  # live stack (docker compose up -d)
(cd projects/mini-rag && uv run pytest --cov)         # pilot unit tests, coverage >= 70 %
```

## Further reading

- `ARCHITECTURE.md`: the stack, the layers and the data flow in detail.
- `decisions.md`: why things are the way they are (ADRs).
- `contracts/EXPERIMENT.md`: the experiment contract (layout, `run.json` ledger, `split.json`).
- `IMPLEMENTATION_STATUS.md`: what is built and what is pending.
