# Implementation Plan — experiment kind `exploration`

**Date:** 2026-11-09 · **Phases:** 1 · **Agent:** `general-purpose` (Python + TypeScript + Markdown) · **Base:** `main` @ `ab70a8d`
**Feature (inline, no issue):** a third experiment kind for work that is neither training nor a candidate comparison
(exploring data, trying an architecture, a benchmark). Sequence `scoping → eda → report`: no dataset step, no split,
no modeling, no audit, no tracking. The user, 2026-11-09: "le jeu de données n'est pas nécessaire, ça fait partie de
la flexibilité".

## Scope Analysis

| Area | New | Modified |
|------|-----|----------|
| Contract | — | `contracts/milestones.json`, `contracts/value_sets.json`, `contracts/run_ledger_vectors.json`, `contracts/EXPERIMENT.md`, `contracts/README.md` |
| `datalab` (pure) | — | `ledger_model.py`, `ledger_rules.py`, `ledger_ops.py` |
| Template | — | `templates/project/src/__DATALAB_PACKAGE__/prepare.py`, `templates/project/tests/test_train_frozen.py` |
| Hook | — | `tools/pre_commit_checks/check_enum_discipline.py` |
| App | — | `app/src/lib/ledger.ts`, `app/src/lib/ledger.test.ts`, `app/src/lib/best.ts`, `app/src/lib/best.test.ts` |
| Skill | — | `.claude/skills/experiment/SKILL.md`, `references/dispatch-briefs.md`, `references/agent-overrides.md` |
| Tests | — | `packages/datalab/tests/test_ledger.py`, `test_ledger_io.py`, `tests/TESTING_SCENARIOS.md` |
| Docs | — | `ARCHITECTURE.md` (orchestrator), `decisions.md` ADR (orchestrator) |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | decision | `exploration` sequence is `scoping, eda, report`; dataset, split, modeling, audit and tracking do not exist for it | — | — |
| D-2 | decision | no new invariant ids: I-7, I-10, I-11, I-13, I-14, I-15 each gain an "absent milestone ⇒ its field is null/empty" branch | — | — |
| D-3 | decision | `metric` stays required for every kind (card `metric:` + V-3 unchanged); an exploration states what it looks at as its metric line | — | — |
| D-4 | decision | ops that belong to absent milestones (`freeze_split`, `record_data`) refuse an exploration ledger with a named message instead of a `KeyError` | — | — |
| D-5 | decision | an exploration may log MLflow runs, from its own project code via `datalab.tracking` (flat runs). The template `train`/`eval` refuse an exploration ledger by name, because they need a frozen split | — | — |
| D-6 | decision | the card's best run for an exploration follows the legacy rule (every FINISHED run it admits, ranked on the card metric), so a benchmark's runs show | — | — |

## Existing Equivalents

| Mechanism | Existing code | Plan |
|-----------|---------------|------|
| sequences per kind | `contracts/milestones.json:7-9` + `ledger_model.contract()` | add one key |
| kind enum, both sides | `ledger_model.py:38`, `app/src/lib/ledger.ts:9,23`, `contracts/value_sets.json` | add one value |
| "field only when its milestone exists" | I-7 (`ledger_rules.py:66-69`, comparison has no features) | generalise the same shape |
| milestone-guarded reset | `ledger_ops.redo` (`anchor in seq`, `:145`) | already kind-safe |
| card rule without a ledger | `app/src/lib/best.ts:47-51` (`bestFilter` → `legacy`) | reuse for exploration (D-6) |
| template refusals before any run | `prepare.py` `PrepareError` (`frozen_score_on`) | add one refusal (D-5) |
| stepper | `app/src/components/Stepper.astro` reads `toSteps` from the contract | no change |
| shared cases | `contracts/run_ledger_vectors.json` (`rule`, `checked_by`) | add vectors |

## Simplicity Review

Before → after: 1 phase → 1 phase · ~18 edits → ~15 (reviewer: simplicity-reviewer, 2026-11-09). Verdict: not overbuilt.

| # | Action | Class | What | Disposition |
|---|--------|-------|------|-------------|
| S-1 | simplify | mechanism | one private `_absent` message helper in `ledger_rules` instead of a public `article()` | applied |
| S-2 | simplify | mechanism | `record_data` / `test_access_problem` already refuse an exploration; pin with tests, no new branch | applied |
| S-3 | keep | mechanism | `bestFilter` exploration → `legacy` (every FINISHED run the legacy rule admits) | applied (D-6 wording) |
| S-4 | keep | mechanism | template `frozen_score_on` refuses an exploration by name | kept |
| S-5 | drop | mechanism | the extra I-1 exploration vectors (I-1 is kind-agnostic, already covered) | applied |
| S-6 | simplify | mechanism | no §7/§8 skill edits (already milestone-anchored); one §5 sentence | applied |
| S-7 | keep | mechanism | `ds-eda` override row (else `ds-eda.md:35` stops without split.json) | kept |
| S-8 | add | — | "two sequences" / kind lists in EXPERIMENT.md:28, contracts/README.md:7, SKILL.md:42-43, ARCHITECTURE.md:390 | applied |
| S-9 | keep | mechanism | the six "absent milestone ⇒ field null" guards (real crashes + skill writes dataset raw) | kept |

## Mechanical Rules to Enforce

| Rule | Apply at phase | Recipe match | Scaffold command |
|------|---------------|--------------|------------------|
| `"exploration"` compared only as `Kind.EXPLORATION` | 1 | existing `check_enum_discipline.py` (add the literal) | none (existing hook) |

## CI Gate Surface

| Gate | Laid by | At phase |
|------|---------|----------|
| ruff, pyright, pytest + coverage (`packages/datalab`), app lint/check/test, ledger hook, enum discipline | already present | unchanged |

## Failure Modes (resilience)

No external trust boundary crossed: pure ledger rules and the existing read path. No failure modes to enumerate.

## Unspecified Behaviors (spec-gap)

Decision points: the ledger invariants and the ops for a kind that lacks milestones (decided here, SAFE-DEFAULT).

| # | Behavior | Decided resolution | Required test | Phase |
|---|----------|--------------------|---------------|-------|
| U-1 | exploration ledger with `dataset` set | I-11 refuses | vector `exploration-with-dataset` | 1 |
| U-2 | exploration with `split_sha256` or `split_summary` set | I-10 refuses | vector `exploration-with-split` | 1 |
| U-3 | exploration with `features` | I-7 refuses: `I-7: features is not in the exploration sequence, so features must be null` | vector `exploration-with-features` | 1 |
| U-4 | exploration with `winner` / `data_sha256` / a test look | I-13 / I-15 / I-14 refuse | vectors `exploration-with-winner`, `-data-hash`, `-test-look` | 1 |
| U-5 | `freeze_split` / `record_data` on an exploration | `LedgerError` (freeze: new guard naming the sequence; record_data: the existing "split must be frozen" refusal) | `test_freeze_split_refuses_exploration`, `test_record_data_refuses_exploration` | 1 |
| U-6 | `redo("scoping")` on a finished exploration | resets all three to todo; no field to clear | `test_redo_exploration_resets_all` | 1 |
| U-7 | the kind is still fixed after scoping (U-17) | unchanged: archive and restart | covered by the existing write-refuses-kind-change test | 1 |
| U-8 | card of an exploration with finished runs | legacy rule (D-6) | `best.test.ts`: `bestFilter` on an ok exploration state → `{kind:'legacy'}` | 1 |
| U-9 | template `train` on an exploration ledger | `PrepareError`, exit 2, before any run (D-5) | `test_train_refuses_exploration_ledger_before_any_run` | 1 |
| U-10 | `eval` / `test_access_problem` on an exploration | refused by the existing audit check (no code change) | `test_test_access_refuses_exploration` | 1 |
| U-11 | an exploration with no runs and no meaningful metric | metric stays required (D-3); the card shows "no runs" as today | none new (existing card tests) | 1 |

---

## Phase 1 — per-file specs

Read `contracts/EXPERIMENT.md` §2 and `ARCHITECTURE.md` "Experiment milestone" first. Every message below starts with
its rule id (the check order is unchanged: first failure wins).

#### `contracts/milestones.json` (MODIFY)
Add `"exploration": ["scoping", "eda", "report"]` to `sequences`. Keep `freeze_after: "dataset"` (it is absent from
the exploration sequence; the code treats that as "no split").

#### `contracts/value_sets.json` (MODIFY)
`kinds`: `["training", "comparison", "exploration"]`.

#### `packages/datalab/src/datalab/ledger_model.py` (MODIFY)
`Kind` gains `EXPLORATION = "exploration"` (appended last, the order the copy-checks expect).
`contract()` already demands `set(sequences) == set(Kind)`: no change there.

#### `packages/datalab/src/datalab/ledger_rules.py` (MODIFY)
Add one private pure helper, `_absent(lg, anchor: str, *fields: str) -> str | None`. When `anchor` is not in
`lg.sequence()` and any of `fields` is set on the ledger (not `None`, or a non-empty tuple for `test_looks`), it
returns `f"{anchor} is not in the {lg.kind} sequence, so {' and '.join(fields)} must be {'empty' if fields ==
('test_looks',) else 'null'}"`. Otherwise it returns `None`. Each rule below opens with the guard, and the rest of
the rule runs only when the anchor is in the sequence. The vectors pin only the rule prefix (`test_ledger.py:31-44`,
`ledger.test.ts:34-38`), so new wording is safe.
- `_i7`: replace the `Kind.COMPARISON` test with `if (m := _absent(lg, FEATURES, "features")): return f"I-7: {m}"`.
  The comparison message changes to the same shape; nothing pins its text.
- `_i10`: `_absent(lg, contract().freeze_after, "split_sha256", "split_summary")` → `I-10: …`; when the anchor is
  absent and the fields are null, return `None` before the existing `seq.index(...)`.
- `_i11`: `_absent(lg, DATASET, "dataset")`; `_i13`: `_absent(lg, MODELING, "winner")`;
  `_i14`: `_absent(lg, AUDIT, "test_looks")`; `_i15`: `_absent(lg, MODELING, "data_sha256")`. Each returns
  `None` right after the guard when the anchor is absent.
- Import `FEATURES` and `AUDIT` from `ledger_model` (`DATASET`, `MODELING` are already imported); `Kind` may become
  unused (remove it if so). Stay ≤ 200 lines (now 149).

#### `packages/datalab/src/datalab/ledger_ops.py` (MODIFY)
- `freeze_split`: first line `if contract().freeze_after not in lg.sequence(): raise LedgerError(f"{freeze_after} is
  not in the {lg.kind} sequence: there is no split to freeze")`. This is the only op that would `KeyError` (`:151`).
- `record_data`: unchanged. On an exploration its existing first check (`split_sha256 is None`, `:164`) already
  refuses before the `MODELING` lookup. Pinned by a test below.
- Nothing else: `new_ledger`, `produce`, `decide`, `redo` are already sequence-driven.

`ledger_access.py` is unchanged. On an exploration, `test_access_problem` already refuses at `current_milestone !=
AUDIT` (`:12-13`, and I-6 keeps the pointer inside the sequence). Pinned by a test below; the template `eval` goes
through it and exits 2.

#### `templates/project/src/__DATALAB_PACKAGE__/prepare.py` (MODIFY)
`frozen_score_on`: right after `lg = read_ledger(experiment_dir)`, add
`if lg is not None and lg.kind is Kind.EXPLORATION: raise PrepareError("an exploration ledger has no train run: log
runs from project code with datalab.tracking, or archive run.json and restart with another kind")` (`Kind` is
already imported). The template `eval` is already refused by `test_access_problem` (above), with exit 2.

#### `templates/project/tests/test_train_frozen.py` (MODIFY)
Add `test_train_refuses_exploration_ledger_before_any_run`, with the same fixtures as
`test_train_refuses_split_changed_after_freeze_before_any_run` (`:20`: `configs, exp_dir, data_overrides, tracking,
capsys`). Given: `ledger.write_atomic(exp_dir, ledger.new_ledger(ledger.Kind.EXPLORATION, "score (max): x"))`.
Expected: `_train(configs, data_overrides) == 2`, `"an exploration ledger has no train run"` in
`capsys.readouterr().err`, and `MlflowClient(tracking).get_experiment_by_name(E) is None`. These template tests run only under `pytest -m scaffold` (CI). Run that locally too.

#### `app/src/lib/best.ts` (MODIFY)
`bestFilter`: when `state.kind === 'ok' && state.ledgerKind === 'exploration'`, return `{ kind: 'legacy' }`. Update
the `BestFilter` doc comment: "`legacy`: no run.json, or an exploration ledger (D-6)". Nothing else changes.

#### `app/src/lib/best.test.ts` (MODIFY)
Next to the `bestFilter` asserts (`:65-66`): `bestFilter(<ok state with ledgerKind 'exploration', null hashes>)`
deep-equals `{ kind: 'legacy' }`; the same state with `ledgerKind 'comparison'` still gives `{ kind: 'ledger',
splitSha256: null, dataSha256: null }`.

#### `tests/TESTING_SCENARIOS.md` (MODIFY)
After EXP-05, add rows in the same 6-column format: `EXP-NN | Exploration ledger runs to report |
new_ledger(kind=exploration) → produce/validate scoping, eda, report → validate | exit 0, no split/dataset fields |
🆕 New | exploration Phase 1`. Add a second row: `Exploration → training via archive | §11 archive run.json, new
ledger kind=training | the old ledger kept as run.<date>.json, new one at scoping`. Use the next free EXP numbers.

#### `tools/pre_commit_checks/check_enum_discipline.py` (MODIFY)
Add `"exploration": "Kind.EXPLORATION"` next to `"comparison"` (line 38).

#### `contracts/run_ledger_vectors.json` (MODIFY)
Follow the shape of the existing entries (`name`, `run`; invalid ones add `rule`, `checked_by`).
- valid: `fresh-exploration` (scoping `todo`, every field null/empty, metric e.g. `"coverage (max): share of rows
  with a usable transcript"`), `exploration-complete` (three milestones validated, artifacts `scope.md`, `eda.md`,
  `reports/report.html`, three `validate` log entries, `current_milestone` `report`).
- invalid (`checked_by: ["python"]`), each = `exploration-complete` plus one field: `exploration-with-dataset`
  (I-11), `exploration-with-split` (I-10, `split_sha256` = 64×`a`), `exploration-with-features` (I-7),
  `exploration-with-winner` (I-13), `exploration-with-data-hash` (I-15), `exploration-with-test-look` (I-14).
- No new I-1 vector: I-1 is kind-agnostic and `exploration-complete` already exercises the exploration sequence
  lookup in both vector loops.

#### `app/src/lib/ledger.ts` (MODIFY)
`KINDS = ['training', 'comparison', 'exploration']`; the `sequences` zod object gains `exploration:
z.array(z.string())` (stays `.strict()`). Nothing else: `STEP_AGENTS` and `toSteps` iterate `KINDS`.

#### `app/src/lib/ledger.test.ts` (MODIFY)
Next to the sequence-length asserts (line 84-85): `assert.equal(MILESTONES.sequences.exploration.length, 3)`. Add a
test: `readLedger` on `exploration-complete` → `ledgerKind === 'exploration'`, steps ids `['scoping','eda','report']`,
all `validated`, none `current`. The vector loop already covers the new app vectors.

#### `packages/datalab/tests/test_ledger.py` and `test_ledger_io.py` (MODIFY)
| Test | Given → expected | Source |
|---|---|---|
| `test_contract_matches_kind_enum` (update) | sequences `exploration` == `("scoping", "eda", "report")` | D-1 |
| `test_new_exploration_ledger_starts_at_scoping` | `new_ledger(Kind.EXPLORATION, "m (max): x")` → current `scoping`, 3 milestones todo | D-1 |
| `test_exploration_runs_to_report` | produce+validate scoping, eda, report → all validated, current `report`, `validate_dir` OK with the artifacts on disk | D-1 |
| `test_freeze_split_refuses_exploration` | exploration with scoping validated → `LedgerError` matching `"dataset is not in the exploration sequence"` (not `KeyError`) | U-5 |
| `test_record_data_refuses_exploration` | same ledger → `LedgerError` matching `"the split must be frozen"` | U-5 |
| `test_redo_exploration_resets_all` | `exploration-complete`, `redo("scoping")` → 3 todo, current `scoping`, fields still null | U-6 |
| `test_test_access_refuses_exploration` | `exploration-complete`, sha `"a"*64` → `test_access_problem` == `"the test partition is read at the audit; the current milestone is report"`; `record_test_look` raises `LedgerError` | U-10 |
| `test_f_18_ledger_vectors` | the new vectors, each with its rule prefix | U-1..U-4 |

#### `contracts/EXPERIMENT.md` (MODIFY)
Intro: `kind: training | comparison | exploration`; §2 (`:28`) "the two sequences" → "the three sequences". Add one paragraph: an exploration has no dataset
step, split, modeling, audit or tracking; its dataset/split/features/winner/data hash stay null and `test_looks`
empty (I-7, I-10, I-11, I-13, I-14, I-15). Its runs, if any, come from project code via `datalab.tracking` (the
template train/eval refuse it), and the card ranks them like a project without run.json (D-5, D-6).

#### `contracts/README.md` (MODIFY)
Line 7: "the two sequences" → "the three sequences" (training, comparison, exploration).

#### `.claude/skills/experiment/SKILL.md` (MODIFY)
- §3c: ask the kind among training | comparison | exploration; one line on when to pick exploration (look at data,
  try an architecture, benchmark without a frozen test).
- §5: one sentence: "a transition whose milestone is absent from the sequence never runs; an exploration is scoping →
  eda → report, and logs runs (if any) from project code with `datalab.tracking`".
- §1 table row on `run.json`: `kind` (training | comparison | exploration).
- §2 (`:42-43`): `(or Kind.COMPARISON)` → `(or Kind.COMPARISON / Kind.EXPLORATION)`.

#### `.claude/skills/experiment/references/dispatch-briefs.md` (MODIFY)
`eda`: add "An exploration: the data `scope.md` names (any source), no `split.json`, every row readable." `report`:
"An exploration: `PROJECT.md`, `run.json`, `scope.md`, `eda.md` only."

#### `.claude/skills/experiment/references/agent-overrides.md` (MODIFY)
`ds-eda` row: add "in an exploration there is no split.json: read the data scope.md names; never invent a split".

**Run after implementing:** `cd packages/datalab && uv run --locked ruff check . && uv run --locked pyright -p
pyproject.toml && uv run --locked pytest -q --cov && uv run --locked pytest -q -m scaffold`; `cd app && npm run lint && npm run check && npm test`;
`uv run --locked --project packages/datalab python -m datalab.ledger validate projects/*`; `pre-commit run
--all-files`.

<!-- plan-validate: READY 2026-11-09 sha256:0cba21568fd8 -->
