# Implementation Plan — experiment methodology (trouvetou in data-lab)

**Date:** 2026-11-06 (revised after two ❌ NOT READY validations) · **Feature:** every data-lab experiment follows
trouvetou's methodology — a stepper skill with expert validation per milestone, a frozen dev/test split, the metric
restated at every step, a ledger-gated test read, an adversarial audit, Hydra-wired code with an in-process grid search,
clean nested MLflow runs, and a read-only app view of the stepper · **Phases:** 5 · **Base:** `main` @ a2e1201

> ⚠️ Planned with review debt: 3 cycles un-reviewed (user override 2026-11-06).

Motivation: voice-arch (built by an autonomous loop) tuned fixes on the eval persona, had a metric dominated by STT
garble, unlogged one-off calls, candidate names inside metric keys, and knobs in code.

| Phase | Title | Files | Agent | Depends on |
|-------|-------|-------|-------|------------|
| 1 | Experiment contract + datalab ledger, split, tags and trial helpers | 22 | `python-fastapi` | — |
| 2 | Hydra gate, ledger hook, `datalab-new` wiring, CI matrix | 11 | `python-fastapi` | 1 |
| 3 | Hydra project template (grid, eval gate), package name, scaffold-and-gate | 37 | `python-fastapi` | 1, 2 |
| 4 | `/experiment` skill (Markdown skill + 2 references) | 3 | `general-purpose` | 1, 2, 3 |
| 5 | App stepper + run groups + ledger-aware card best (read-only) | 30 | `general-purpose` (Astro/TS) | 1 |

Per-file specs live in `IMPLEMENTATION_PLAN_EXPERIMENT_PHASE_{1..5}.md`; each is self-contained. Plan checks (both must
exit 0): `python3 ~/.claude/recipes/plan-tools/scope_ledger.py 'IMPLEMENTATION_PLAN_EXPERIMENT*.md'` and
`python3 ~/.claude/recipes/deferred-tracker/deferred_scan.py --plan 'IMPLEMENTATION_PLAN_EXPERIMENT*.md'`.

## Existing Equivalents

| Mechanism | Existing code (path:line, `main` @ a2e1201) | Plan |
|-----------|---------------------------------------------|------|
| Atomic publish | `packages/datalab/src/datalab/new_project.py:72-77` (tmp dir + `os.rename`) | same shape for `write_atomic` (+ fsync, `os.replace`) |
| Shared Python/TS vectors | `contracts/name_vectors.json`, read by `packages/datalab/tests/test_project.py:26-32` and `app/src/lib/name.test.ts:7-9` | same pattern: `contracts/{run_ledger_vectors,milestones,mlflow_tags}.json` |
| Tagged MLflow run | `packages/datalab/src/datalab/tracking.py:49-67` (`tracked_run`, non-overridable `project` tag) | API unchanged; add `tracked_trial` (nested child) |
| Budget from MLflow | `projects/voice-arch/src/voice_arch/budget.py:22-39` (sum of `cost_usd`, `ViewType.ALL`, paginated) | generalised as `project_spend` (displayed, not enforced) |
| Experiment filter `p` / `p/<sub>` | `app/src/lib/mlflow.ts:87,93-94` (LIKE, then exact/prefix filter) | mirrored in Python enumeration |
| Purity contract | `packages/datalab/pyproject.toml:38-42`, `projects/mini-rag/pyproject.toml:44-52` | extended to the new datalab modules; template contract on `scoring`/`candidates`/`grid` |
| Subprocess justification | `new_project.py:47` (`# noqa: S603  # <reason>`) | same comment in `hydra_gate.py` and template tests |
| Per-project hooks | `.pre-commit-config.yaml:34-46` (declared-deps-*), `:56-69` (gates-*) | moved into marker regions that `datalab-new` writes |
| Per-project CI jobs | `.github/workflows/ci.yml:74-116` (`pilot`, `voice-arch`) | one `projects` matrix job |
| Hydra wiring gate | `~/.claude/skills/trouvetou/assets/check_hydra_project.py` (136 lines, sha256 `312f6242…61b2`) | vendored verbatim to `tools/` |
| Milestone + split + ledger contract | `~/.claude/skills/trouvetou/CONTRACTS.md:84-173` | adapted (kind, `todo`, strict order, test looks, winner) in `contracts/EXPERIMENT.md` |
| Test isolation | `packages/datalab/tests/conftest.py:13-30` (`_isolated`, `sqlite_uri`) | copied into the template conftest |
| Template placeholders | `new_project.py:16,30-39` (`__DATALAB_PROJECT__`, `__DATALAB_TITLE__`, content only) | add `__DATALAB_PACKAGE__` + path rename |
| Build report + strict export | `app/src/lib/report.ts:5-13`, `app/src/integrations/export-guard.ts:6-12` | add a ledger entry kind |
| Card best run | `app/src/lib/mlflow.ts:60-82` (`pickBest`), `:97-113` (FINISHED only) | `pickBest` moved to leaf `best.ts`, run on eligible children of the frozen split |
| MLflow REST shapes | `app/src/lib/mlflow-rest.ts:9-19` (no tags, no paging) | add tags, status, paging |
| Stepper UI / ledger | none | new (Phases 1, 5) |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | decision | shared MLflow server on 5050, not trouvetou's per-project sqlite (deviation from trouvetou) | — | — |
| D-2 | decision | one template for every kind; `kind` stored in run.json, no `--kind` flag | — | — |
| D-3 | defer | voice-arch pilot + mini-rag migration through `/experiment` happen after this plan, in their own cycle | #28 | user, AskUserQuestion 2026-11-06 |
| D-4 | decision | search = grid in-process (one child per combination, `configs/hparams_search/<name>.yaml`), no `--multirun` | — | — |
| D-5 | decision | child runs (one per grid combination, full eval set) carry `metric.key` and `cost_usd`; parents carry neither | — | — |
| D-6 | cut | BOX budget is displayed at the BOX pause, not enforced by train (trouvetou wants a hard stop) | #28 | user, AskUserQuestion 2026-11-06 |

## User decisions (2026-11-06, via AskUserQuestion)

1. **Test gate** — `eval` exits 2 and opens no MLflow run unless run.json exists with `current_milestone == "audit"` and
   audit `todo|produced`; each eval run tags `test_look=<n>`; a 2nd+ look on one `split_sha256` needs an expert note,
   recorded in run.json `test_looks: [{split_sha256, run_id, note}]` (I-14). Helper `ledger.test_access_allowed` /
   `test_access_problem` in Phase 1, gate in the template `eval` (Phase 3).
2. **Hyperparameter search** — minimal grid expander in template `train.run`: `configs/hparams_search/<name>.yaml` =
   per-candidate lists; one child per combination, `run_name` `<family>-<i>`, tag `candidate` = family, params logged;
   `tracked_trial(..., *, candidate=None)`; outcome registry `datalab.tracking._OUTCOMES` (dict keyed by parent run id,
   popped by `tracked_run`); a grid naming an unknown candidate → exit 2. D-4.
3. **Budget = display only** — the skill shows `project_spend` and the BOX budget at the BOX ⏸️; train never stops on it. D-6.
4. **Card best** — train tags parents `split_sha256`, `data_sha256`, `score_on`; the card ranks only children whose parent
   matches run.json's `split_sha256` and `data_sha256` (legacy projects without run.json keep today's rule); run.json
   `winner: {candidate, run_id} | null`, non-null iff modeling is validated (I-13); eval defaults to the winner and
   refuses when the model config hash differs from the winning child's `config_sha256` tag.
5. **D-3** retyped `defer`, tracker #28 ("Migrate voice-arch and mini-rag … via /experiment").

## Simplicity Review

Before → after: 5 phases → 4 (S-1, then a size split) → 5 (validator fix: the old Phase 2 split into gates and
template) · reviewer: fable, 2026-11-06

| # | Action | Class | What | Disposition |
|---|--------|-------|------|-------------|
| S-1 | simplify | mechanism | 5 → 3 phases | applied, then split for size and reviewability → 5 |
| S-2 | simplify | mechanism | one MLflow level carries `metric.key` + `cost_usd` (children); no role tag, no parents-only query | applied (D-5) |
| S-3 | drop | mechanism | generic per-project runner + legacy marker → path-scoped hooks, legacy skip by path absence, parity test | applied |
| S-4 | simplify | mechanism | explicit CI matrix list | applied |
| S-5 | drop | mechanism | `--kind` and two template shapes → one template, kind in run.json | applied (D-2) |
| S-6 | simplify | mechanism | trouvetou milestone ids, sequence listed in the ledger | applied |
| S-7 | drop | mechanism | `ledger.md` → PROJECT.md narrative | applied |
| S-8 | drop | mechanism | mlflow import-linter wrapper → template purity contract | applied |
| S-9 | simplify | mechanism | ledger module + `validate` entry only | applied (pure transitions in `ledger_ops`, CLI keeps `validate` only) |
| S-10 | keep | mechanism | vendor `check_hydra_project.py` verbatim | applied (wrapper separate, F-1) |
| S-11 | defer | capability | app stepper to its own cycle | kept by user (Phase 5) |
| S-12 | simplify | mechanism | split.json `grouped` strategy for personas | applied |
| S-13 | add | — | template test without an MLflow server (sqlite) | applied, Phase 3 |
| S-14 | add | — | Hydra confirmed before code | user confirmed 2026-11-06 |

## Cross-phase dependencies

- **1 → 2:** `python -m datalab.ledger validate <path>...` (hook + CI step), `contracts/EXPERIMENT.md`.
- **1 → 3:** `datalab.split` (`Partition`, `Split`, `read_split`, `split_sha256`), `datalab.ledger` (`read`,
  `write_atomic`, `test_access_problem`, `record_test_look`, `look_number`, ops for the eval fixture),
  `datalab.project.card_metric`, `datalab.tags.Tag`, `tracked_trial(..., candidate=)` / `Trial.add_cost`.
- **2 → 3:** `wiring.plan/apply` inside `datalab-new`, `fake_repo` with both config files, `hydra_gate.main(argv, *,
  repo_root)` (the scaffold test asserts it ran).
- **1 → 4:** ledger transitions (`new_ledger`, `produce`, `decide(.., winner=)`, `redo`, `freeze_split`, `record_data`,
  `write_atomic`), `project_spend`, `stale_runs`, `close_runs`, `contracts/milestones.json`.
- **2, 3 → 4:** template layout (`configs/{train,eval}.yaml`, `python -m <pkg>.train` / `.eval`), the grid, the eval
  gate, hooks `hydra-gate` + `ledger`, `tools/pre_commit_checks/hydra_gate.py`.
- **1 → 5:** `contracts/{milestones,run_ledger_vectors,mlflow_tags}.json` (exact shapes in Phase 1), run tags
  `mlflow.parentRunId`, `candidate`, `split=test`, `split_sha256`, `data_sha256` (contract in `contracts/EXPERIMENT.md`).

## Mechanical Rules to Enforce

| Rule | Apply at phase | Recipe match | Scaffold command |
|------|---------------|--------------|------------------|
| src modules ≤ 200 lines | already active | `tools/check_file_size.py` (hook `file-size`) | none (exists) |
| Hydra wired in every project with `configs/` | Phase 2 | none — vendored trouvetou gate + `tools/pre_commit_checks/hydra_gate.py` | none (custom) |
| No `${oc.env:...}` in `configs/` | Phase 2 | none — check inside `hydra_gate.py` | none (custom) |
| run.json / split.json valid | Phase 2 | none — `python -m datalab.ledger validate` hook + CI matrix step | none (custom) |
| Every `projects/*` has its hooks + CI matrix entry + gate steps | Phase 2 | none — `datalab.wiring.parity_problems` test | none (custom) |
| datalab pure modules import no mlflow/weaviate | Phase 1 | import-linter `forbidden` (`packages/datalab/pyproject.toml:38-42`) | none (pyproject contract) |
| `scoring`/`candidates`/`grid` import no I/O framework | Phase 3 | import-linter `forbidden` (pattern `projects/mini-rag/pyproject.toml:48-52`) | none (pyproject contract) |
| Tag names from one source | Phase 1 / 5 | none — `contracts/mlflow_tags.json` compared by both suites | none (custom) |
| StrEnum for closed sets | review only | `python-fastapi-layered/check_strenum_only.py` exists | not scaffolded: 6 enums, reviewed in `/check` |

## CI Gate Surface

| Gate | Laid by | At phase |
|------|---------|----------|
| Hook runner (pre-commit + pre-push), ruff, gitleaks, file size, declared deps, per-tree gates, CI-parity workflow | already present (`.pre-commit-config.yaml`, `.github/workflows/ci.yml`) | already present |
| datalab tests + coverage floor 70 % (`packages/datalab/pyproject.toml:59` `fail_under = 70`) | already present (`gates-datalab`, CI `checks`) | stays a failing floor; Phases 1-3 tests run under it |
| Project tests + coverage floor 70 % (template `fail_under = 70`) | already present per project | Phase 2: every new project gets `gates-<name>` + a CI matrix entry (`datalab-new`), parity test fails otherwise |
| Hydra gate + ledger hook + ledger CI step | Phase 2 | Phase 2 (path-scoped; legacy projects skip by path absence) |
| Scaffold-and-gate (fresh project green on its gates) | Phase 3 (`checks` job step, `pytest -m scaffold`) | Phase 3 |
| App tests + line coverage floor 70 % (`app/package.json` `--test-coverage-lines=70`) | already present (`gates-app`, CI `app`) | stays a failing floor; Phase 5 adds the ledger fixture build steps |

Branch protection: the required checks `pilot` and `voice-arch` become `project (mini-rag)` / `project (voice-arch)`;
the user updates the required-check names after Phase 2 merges.

## Failure Modes (resilience)

Trust boundaries crossed: filesystem (ledger, split, template) · subprocess (hooks, uv) · network (MLflow REST,
uv lock) · untrusted config (Hydra YAML, run.json in the app) · money (cost_usd, displayed).

| # | Failure mode | Dimension | Required handling | Required test | Phase |
|---|--------------|-----------|-------------------|---------------|-------|
| F-1 🔴 | hooks pass file names, the gate takes one dir | subprocess | `hydra_gate.py` maps changed paths → unique project roots, one gate run per root; ledger CLI maps file paths → project dirs, `uv run --project` (cwd kept) | `test_f_1_hook_entry_with_two_changed_configs_in_one_project_exits_0`, `test_f_1_ledger_hook_given_file_paths_validates_their_project` | 2 |
| F-2 🟡 | Hydra hook misses src/pyproject changes | config | files regex `^projects/[^/]+/(configs/\|src/\|pyproject\.toml)`, only projects with `configs/` | `test_f_2_hydra_hook_files_regex_matches_src_and_pyproject` | 2 |
| F-3 🟡 | fresh project red on its own gates | contract | CI step scaffolds a project and runs every gate, incl. ruff, file size, pip-audit, the Hydra gate (asserted run) | `test_f_3_scaffolded_project_passes_its_gates` (marker `scaffold`, network) | 3 |
| F-4 🔴 | split edited after freeze / overlapping partitions / indices drift from the cleaned rows | state | `split_sha256` in run.json; V-2 mismatch fails; eval refuses a changed split or data; no overlap; index lists address `data_file` rows and must cover `range(len(rows))`; cleaning keeps row count and order | `test_f_4_split_changed_after_freeze_fails_validate`, `test_f_4_overlapping_groups_rejected`, `test_eval_refuses_changed_split_or_data`, `test_load_split_index_split_not_covering_rows_rejected` | 1 / 3 |
| F-5 🟡 | ledger drifts from the invariants | state | pydantic `strict=True`, `extra="forbid"`, typed `LedgerError`, no fallback, fixed check order | `test_f_18_ledger_vectors[<name>]`, `test_f_5_unknown_key_rejected_not_dropped`, `test_f_5_read_corrupt_raises_ledger_error` | 1 |
| F-6 🟡 | crash mid-write leaves half a ledger | partial failure | validate first (`ValidationError` → `LedgerError`); unique `*.json.tmp`, fsync, `os.replace`, tmp removed on error; gitignored | `test_f_6_serializer_failure_leaves_run_json_byte_identical_and_no_tmp`, `test_f_6_invalid_model_never_written` | 1 |
| F-7 🟡 | money spent but not counted or not seen | money | `Trial.add_cost` logs at once, `tracked_trial` again in `finally`; `project_spend` sums every status incl. RUNNING, 0.0 without an experiment; shown at the BOX (D-6) | `test_f_7_failed_child_still_logs_cost_usd`, `test_f_7_budget_counts_running_runs`, `test_project_spend_without_experiment_is_zero`; skill check 7 | 1 / 4 |
| F-8 🟡 | one candidate fails silently | observability | parent tags `n_children`, `n_failed`, `failed_candidates`; train exits 1; a tracking error is re-raised, never a candidate failure | `test_f_8_parent_lists_failed_candidates`, `test_f_8_one_failing_candidate_parent_lists_it_and_exit_nonzero`, `test_tracking_error_is_not_a_candidate_failure` | 1 / 3 |
| F-9 🟡 | crashed process strands RUNNING runs | crash recovery | `stale_runs` lists (> 24 h); the expert picks; `close_runs(ids)` → KILLED; no automatic kill | `test_f_9_stale_runs_listed_not_closed`, `test_f_9_close_runs_kills_only_given_ids`; skill check 14 | 1 / 4 |
| F-10 🟡 | train depends on cwd / env | cross-platform | project from `__file__`, `version_base=None`, `hydra.job.chdir` false, `hydra.run.dir` under the project | `test_f_10_train_runs_from_foreign_cwd_without_env`, `test_hydra_output_dir_under_project` | 3 |
| F-11 🟡 | bad config found after runs were opened | input | compose + resolve(`throw_on_missing`) + import every combination's `_target_` before any run; user `model=` dropped per candidate | `test_f_11_bad_target_fails_before_any_run_created`, `test_f_11_composes_without_hparams_search`, `test_model_override_dropped_per_candidate` | 3 |
| F-12 🟡 | `--multirun` opens N parallel parents | concurrency | train/eval detect MULTIRUN and exit 2 | `test_f_12_multirun_refused` | 3 |
| F-13 🔴 | test score ranked as the best run | contract | eval logs `test_<metric.key>`, tag `split=test`, experiment `<project>/audit`; the card never ranks it | `test_f_13_eval_logs_test_prefixed_key_not_metric_key`; app F-13 ×2 | 3 + 5 |
| F-14 🟡 | child lands in another experiment / wrong project | contract | `tracked_trial` uses the parent's `experiment_id`, refuses `project`/`candidate` tags, no parent, a trial inside a trial | `test_f_14_child_in_parent_experiment_after_set_experiment`, `test_f_14_trial_refuses_project_or_candidate_tag`, `test_u_20_tracked_trial_refuses_nested_trial` | 1 |
| F-15 🟡 | two trials interleave in one process | concurrency | `tracked_trial` refuses while another is open (threads and asyncio) | `test_f_15_concurrent_trial_refused` | 1 |
| F-16 🟡 | parallel sweeps race on one server | concurrency | ADR: one sweep at a time per MLflow server; a logging failure surfaces as a tracking error (exit 1) | documentation (ADR), no test | 1 |
| F-17 🟡 | one failing project hides the others in CI | observability | matrix `fail-fast: false`; parity test parses ci.yml (`on:` loads as `True`) and requires the Hydra + ledger steps | `test_f_17_ci_matrix_fail_fast_false_and_covers_every_project`, `test_parity_reports_missing_gate_steps` | 2 |
| F-18 🟡 | Python and app disagree on a ledger, a tag or a regex | contract | shared vectors with `checked_by`; same check order; `mlflow_tags.json`; `METRIC_KEY_RE` compared both ways; wiring blocks == the voice-arch stanzas | `test_f_18_ledger_vectors[<name>]`, `test_tag_names_match_contract`, `test_metric_key_re_matches_app_literal`, `test_blocks_reproduce_voice_arch_stanzas_byte_for_byte`; app F-18 ×5 | 1 + 2 + 5 |
| F-19 🟡 | app misses children / pages | external I/O | parse tags (`mlflow.parentRunId`), follow `next_page_token`, all-status query, orphans as their own group | app F-19 ×3 | 5 |
| F-20 🟡 | bad run.json breaks the page or the export | input | missing → no stepper; invalid → badge, page renders, reason in the build report, strict export fails; BOM stripped both sides; CI builds `app/test-fixtures/ledger` | app F-20 ×3 + CI step | 5 |
| F-21 🔴 | test peeked before the audit or re-peeked silently | access | eval reads run.json first; refused (exit 2, no run) outside the audit; looks counted (`test_look`), a 2nd+ look needs a note | `test_f_21_eval_without_ledger_exits_2`, `test_f_21_eval_before_audit_exits_2`, `test_f_21_eval_after_audit_validated_exits_2`, `test_u_28_second_look_needs_note` | 1 / 3 |

Security note: no credential ever sits in a Hydra config (the resolved config is written to `logs/`); `_target_` is
read only from repo YAML; MLflow filter strings interpolate only NAME_RE-checked names.

## Unspecified Behaviors (spec-gap)

Decision points: state change (ledger) · selection (best run, winner) · access (test partition) · scope (budget) · naming.

| # | Behavior (was unstated) | Dimension | Decided resolution | Required test | Phase |
|---|-------------------------|-----------|--------------------|---------------|-------|
| U-1 🔴 | status/decision pairs | state | `todo` ⇒ decision null; `validated` ⇒ `validate`; `produced` ⇒ null or `correct` | `test_f_18_ledger_vectors[validated-with-correct]`, `[todo-with-decision]` | 1 |
| U-2 🔴 | order + redo | state | non-`todo` only after every earlier one is validated; current = first non-validated; `redo(m)` resets m and later; the skill demotes | `[produced-after-unvalidated]`, `[current-not-first-unvalidated]`, `test_u_2_redo_resets_later_milestones_to_todo` | 1 / 4 |
| U-3 🔴 | who may read test | access | `load_split` refuses `Partition.TEST` unless eval asks | `test_u_3_train_entry_refuses_test_partition` | 3 |
| U-4 🔴 | split freeze | state | = F-4 | F-4 tests | 1 |
| U-5 🔴 | which candidates run | selection | explicit `candidates: [a, b]` in `configs/experiment/<name>.yaml` → 1 parent, one child per combination | `test_u_5_train_logs_one_parent_and_one_child_per_listed_candidate` | 3 |
| U-6 🔴 | test score in the card | selection | = F-13 | F-13 tests | 3 / 5 |
| U-7 🔴 | dual-site ledger rules | contract | = F-18 | F-18 tests | 1 / 5 |
| U-8 🔴 | new project unwired | scope | `datalab-new` writes the stanzas + matrix entry; parity test | `test_u_8_new_project_passes_parity_test` | 2 |
| U-9 🟡 | child of an unfinished parent | selection | child counts only if its parent is FINISHED | app U-9 | 5 |
| U-10 🟡 | child naming | naming | `run_name` `<family>-<i>`, tag `candidate` = family (default: run_name) | `test_u_10_trial_name_and_candidate` | 1 |
| U-11 🟡 | group counts | empty | count = FINISHED children; 0 → `0 children, no best`, never hidden | app U-11 ×3 | 5 |
| U-12 🟡 | parentless runs | ordering | standalone rows, `start_time` desc | app U-12 ×2 | 5 |
| U-13 🟡 | trouvetou-format run.json | input | `unsupported schema (kind missing)` on both sides | `[trouvetou-format]`; app F-18 | 1 / 5 |
| U-14 🟡 | milestone keys | state | keys == the kind's sequence exactly | `[milestone-outside-sequence]`, `[sequence-milestone-missing]` | 1 |
| U-15 🟡 | missing artifact | empty | validator V-1: produced artifacts exist and stay inside; app: unlinked `missing` text | `test_u_15_missing_artifact_fails_validate`; app U-15 ×2 | 1 / 5 |
| U-16 🟡 | not-yet values | default | `dataset`, `split_summary`, `features`, `winner`, hashes null until filled; key absence or `[]` refused | `test_u_16_scoping_ledger_with_null_dataset_is_valid`, `[missing-dataset-key]`, `[empty-features]` | 1 |
| U-17 🟡 | kind change / new experiment | state | kind fixed once scoping is validated; the skill archives `run.<YYYY-MM-DD>.json` (also after `report` validated) and starts a new ledger | `test_write_refuses_kind_change_after_scoping_validated`; skill check 13 | 1 / 4 |
| U-18 🟡 | skipped milestones | state | no `skipped` status (user decision: strict order + reset) | `[skipped-status]` | 1 |
| U-19 🟡 | experiment naming | input | `experiment.name` NAME_RE, `audit` reserved; experiment `<project>/<experiment.name>` | `test_u_19_train_refuses_bad_experiment_name` | 3 |
| U-20 🟡 | grandchild runs | state | = F-14 | `test_u_20_tracked_trial_refuses_nested_trial` | 1 |
| U-21 🟡 | hook scope | scope | = F-2 | F-2 test | 2 |
| U-22 🟡 | half-migrated project | state | `configs/` without wired Hydra is red (intended) | `test_u_22_gate_fails_project_with_configs_but_no_hydra_main` | 2 |
| U-23 🟡 | split.json alone | state | valid without run.json; cross-checks only when both exist | `test_u_23_validate_accepts_split_without_run_json` | 1 |
| U-24 🟡 | pre-freeze reads | access | before freeze only target/group_key/time_col; EDA on train+val after; test only via gated eval | skill check 6 + U-3 test | 4 / 3 |
| U-25 🟡 | name → package | naming | the package rule, quoted verbatim under *Defaults stated* (same text in Phase 3 and `contracts/EXPERIMENT.md`) | `test_u_25_package_name_refusals_write_nothing`, `test_package_name_maps_dashes_and_refuses_deps` | 3 |
| U-26 🟡 | grid shape | input | grid keys must be listed candidates and param keys must exist in that candidate's model YAML (else exit 2, before any run); non-empty scalar lists; product over sorted params, index from 0 | `test_u_26_grid_one_child_per_combination`, `test_u_26_grid_naming_unknown_candidate_exits_2`, `test_grid_unknown_param_key_exits_2_before_any_run`, `test_grid_expand_order` | 3 |
| U-27 🔴 | which run the card and the audit use | selection | parents tagged `split_sha256`/`data_sha256`; card (index and project page) ranks children of matching parents only; `winner` ⇔ modeling validated; eval refuses a config hash ≠ the winner's, or a winner whose parent carries another split/data hash | `test_decide_modeling_requires_winner`, `test_u_27_config_hash_mismatch_refused`, `test_eval_refuses_winner_from_another_split`, `test_eval_cli_model_override_reaches_hash_check`, `test_eval_cli_non_dummy_winner_override_form`; app U-27 ×3 | 1 / 3 / 5 |
| U-28 🔴 | repeated test looks | access | `test_looks` append-only; 2nd+ look on one split needs a non-blank note (I-14) | `test_u_28_test_access_rules`, `test_u_28_second_look_needs_note` | 1 / 3 |
| U-29 🟡 | card ↔ ledger metric, metric key hygiene | contract | V-3: run.json `metric` starts with `<card key> (<goal>)`; FINISHED children share one key set ⊆ key + cost_usd + `experiment.metrics`, no candidate-name token | `test_metric_not_matching_card_fails_validate`, `test_metric_key_problems`, `test_u_29_secondary_key_not_declared_exits_1` | 1 / 3 |
| U-30 🟡 | comparison partitions | default | val may be empty; `score_on` → `train` (dev) for comparison, `val` for training; test non-empty | `test_empty_test_rejected`, `test_u_30_comparison_ledger_scores_on_train` | 1 / 3 |

Each behavior above is a phase acceptance criterion. No assumption is left `(unknown — user to confirm)`.
`[name]` = a case of the parametrized `test_f_18_ledger_vectors`.

## Defaults stated

Shown to the user on 2026-11-06; the user may correct any of them. The five user decisions are listed above.

- **Package rule** (validator fix 5, one definition): **`<pkg>` = `name.replace("-", "_")`, refused (exit 2, nothing
  written) when it is a Python keyword, in `sys.stdlib_module_names`, or in `set(importlib.metadata.packages_distributions()) | {"hydra",
  "omegaconf", "antlr4"}` (the import names of the env `datalab-new` runs in, plus the template's Hydra deps)**.
- Sequences: training = scoping, dataset, cleaning, eda, features, modeling, audit, tracking, report; comparison =
  scoping, dataset, eda, modeling, audit, tracking, report. Single source `contracts/milestones.json`.
- **MLflow naming** (resolution): experiment `<project>/<experiment.name>`, `experiment.name` matches NAME_RE;
  `logger.sub` and the `logger/` group are dropped; eval runs go to `<project>/audit` (`audit` reserved as a name); after
  `report` is validated a new experiment archives run.json the same way as a kind change.
- **Comparison kind** (resolution): val may be empty; `score_on` defaults to `train` (= dev) for comparison, `val` for
  training (read from run.json's kind; no run.json → `val`); test non-empty; `EXPERIMENT.md` documents dev/test →
  train/test.
- **Card vs ledger** (resolution): `validate_dir` V-3 requires run.json `metric` to start with `<card metric.key>
  (<goal>)`; the skill sets the card `status: en cours` when scoping is validated and `conclu` when report is validated.
- **Stale runs** (resolution): no automatic kill; `stale_runs` lists RUNNING runs older than 24 h, the skill asks the
  expert, `close_runs` closes only the ids named.
- **Ledger models** (resolution): `ConfigDict(strict=True)` (so JSON-mode validation everywhere); vectors added:
  schema-version-true, empty-metric, empty-dataset-hash, split-sha-uppercase, artifact-backslash, artifact-drive-letter,
  log-decision-mismatch, log-missing-note (invalid), after-redo (valid).
- **Tag names** (resolution): `contracts/mlflow_tags.json` is the single source (11 names); Python `datalab.tags.Tag`
  and app `tags.ts` are compared to it in tests.
- **Metric keys** (resolution): after the sweep train checks every FINISHED child logged the same key set and no key token
  equals a candidate name (exit 1); allowed secondary keys = `experiment.metrics`. Token match (split on `[._/-]`) rather
  than substring, so `core` never flags `score` (plan default).
- **CI** (resolution): the matrix job runs `uv run --locked --project packages/datalab python -m datalab.ledger validate
  projects/${{ matrix.project }}`; the parity test checks the step exists.
- **App** (resolution): strict zod schema + I-1 + rule-id reasons; I-2…I-15, V-1…V-3 Python-only (hook + CI); vectors
  mark `checked_by`; the stepper shows `decisions_log` notes per milestone and no current step once all are validated.
- **Invariant check order** (plan default): JSON → kind present → schema fields (declaration order) → I-1…I-15; first
  failure wins, same on both sides for what the app checks. Invariants raise `PydanticCustomError("ledger_invariant",
  …)`, so messages read `I-n: …`, never pydantic's `Value error, I-n: …`.
- **Split rows** (validator fix): index lists address the rows of `paths.data_file`; cleaning keeps row count and order
  (a drop is a filter applied after partitioning); the template loader refuses a split whose index union ≠
  `range(len(rows))`.
- **Eval CLI** (validator fix): `eval.yaml` carries `model: dummy` and `compose_model` recomposes with `model=<candidate>`
  (no `+`), so `python -m <pkg>.eval model=<winner family> model.<k>=<v>` reaches the config-hash check (the family
  first: a bare `model.<k>=<v>` only parses for `dummy`); grid param keys must exist in the candidate's model YAML
  (struct merge; else exit 2 before any run); the skill passes notes as
  `"look_note='<reason>'"`.
- **`data_sha256`** (plan default): a run.json field distinct from `dataset.hash` (which identifies the source dataset);
  sha256 of the full `paths.data_file`, set by `record_data` at the BOX (after cleaning, so it hashes the file modeling
  trains on), required once modeling is non-`todo` (I-15), cleared by a redo at or before modeling.
- **`config_sha256`** (plan default): sha256 of `json.dumps(resolved model config, sort_keys=True, separators=(",", ":"))`,
  one helper in the template `candidates.py`, tagged on each child by train and recomputed by eval.
- **Who writes `test_looks`** (plan default): eval itself, right after its child run opens (it alone knows the run id),
  with the note from the `look_note=` override that the skill obtained from the expert.
- **Invalid run.json and the card** (plan default): nothing is eligible for best (the badge explains); an absent run.json
  keeps today's rule.
- **Candidate names** match NAME_RE (they appear in `run_name` and in the token check) (plan default).
- `kind` fixed once scoping is validated; `split_sha256` set at freeze; split: no overlap, test non-empty, index lists or
  trouvetou `grouped` / `temporal`; comparison uses `grouped` with group_key persona/question id.
- One sweep at a time per MLflow server (ADR; the Postgres overlay is the escape hatch, not built); credentials only via
  Settings; `${oc.env:...}` refused in configs; a project with `configs/` but no wired Hydra is red until wired.
- trouvetou-format run.json (no kind / no `todo`) is invalid: Python raises, the app shows a badge.
- Card best: only children (they carry `metric.key`); a child counts only if its parent is FINISHED and matches the
  ledger hashes; legacy parentless runs as today when no run.json exists; failed children counted, never best.
- Artifact paths relative to `projects/<name>/` and inside it; the stepper shows them as text (present or `missing`), not
  hyperlinks, because the static export has no route to `projects/` files; an archived ledger never overwrites another
  (`run.<date>-2.json`); the template card declares `metric: {key: score, goal: max}` so the dummy experiment runs.
- BOX budget scope: the whole project (all `<project>/*`), every status; shown, never enforced (D-6).

## Outside this plan

- voice-arch pilot and mini-rag migration through `/experiment` — D-3, tracked in #28.
