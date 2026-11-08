# Fix Plan — Phase 3: Ledger contract, enum discipline & datalab test quality

**Severity:** 🟡
**Agent:**
- python-fastapi for 3.1, 3.2, 3.4–3.9. This is generic Python: ignore the FastAPI layering rules.
- general-purpose for 3.3 (TS in `app/`). It stays inside Phase 3 (accepted by `/plan-fix-validate`): dispatch it as its own subagent, after 3.2. App conventions: Astro 7 + TS strict + `noUncheckedIndexedAccess`; zod from `astro/zod`; tests are `node:test` files `src/lib/*.test.ts` run by `npm test` (coverage floor 70 %); `npm run check` = `astro check`; no `any`, no `@ts-ignore`; exact version pins.

**Depends on:** Phase 2 (2.1 edits template `train.py`, 196/200 lines, before 3.5)
**Fix units:** 9
**Files affected:** 23 (21 existing + 2 new)

Gates: `cd packages/datalab && uv run --locked lint-imports && uv run --locked pyright && uv run --locked pytest -q --cov=datalab`; `cd app && npm run check && npm test`; voice-arch: `cd projects/voice-arch && uv run --locked pyright && uv run --locked pytest -q`.

## Within-phase Dependencies

- 3.1 → 3.4: 3.4 builds the transition table on the post-split `ledger_ops.py`.
- 3.2 → 3.3: the TS test reads the contract file that 3.2 creates.
- 3.2 → 3.5: `Goal` values are in that contract.
- 3.1 → 3.6: 3.6 records the constants that 3.1 introduces.
- 3.1/3.2/3.4 → 3.9: all edit `test_ledger.py`. 3.7 and 3.8 are independent (merged in from the former Phase 7, S-10).

## Fix Units

### Fix Unit 3.1: Split `ledger_ops.py` (199/200) and replace its raw literals (REVIEW §5 row 1, §3 row 3)
- **Files:** `packages/datalab/src/datalab/ledger_ops.py`, `packages/datalab/src/datalab/ledger.py`, `packages/datalab/src/datalab/ledger_model.py`, `packages/datalab/src/datalab/ledger_rules.py`, `packages/datalab/pyproject.toml`, `packages/datalab/tests/test_ledger.py`
- **New files:** `packages/datalab/src/datalab/ledger_access.py`
- **Violation pattern (Grep):** `"status": "|== "modeling"|\["(dataset|modeling|audit)"\]|!= "audit"|"correct" if|status="validated"|\("modeling", \(`
- **Expected after fix:** 0 matches (12 today: 9 in `ledger_ops.py`, 3 in `ledger_rules.py`; the lines that move to `ledger_access.py` must be fixed there too: see the Verification grep)
- **Reference example:** the earlier splits, `ledger.py` → `ledger_checks.py` and `wiring.py` → `wiring_parity.py` (IMPLEMENTATION_NOTES): a pure move, the facade re-imports, and the import-linter pure list grows.
- **HOW TO FIX:**
  1. Move `look_number`, `test_access_problem`, `test_access_allowed`, `record_test_look` and the two `__test__ = False` lines (with their comment) into `ledger_access.py`. Update `ledger.py`'s `from datalab.ledger_ops import (...)` to import them from `ledger_access`. Add `"datalab.ledger_access"` next to `"datalab.ledger_ops"` in the import-linter list in `pyproject.toml` (line ~46).
  2. In `ledger_model.py`, add contract-derived milestone constants: `MODELING: Final = "modeling"`, `AUDIT: Final = "audit"`. Add a test in `test_ledger.py`, `test_named_milestones_exist_in_contract`: both are in `contract().agents`, and `MODELING`, `AUDIT`, `"dataset"`, `"features"` each appear in every sequence they are used against. 3.6 records them (P-10).
  3. Replace every raw literal in both files: `"todo"` → `Status.TODO.value`, `"produced"` → `Status.PRODUCED.value`, `"validated"` → `Status.VALIDATED.value`, `"validate"` → `Decision.VALIDATE.value`, `"correct"` → `Decision.CORRECT.value`, `== "modeling"` / `["modeling"]` / `("modeling", ...)` → `MODELING`, `"audit"` → `AUDIT`. Name the `"dataset"` / `"features"` milestone anchors in `redo`'s `resets` the same way (`DATASET`, `FEATURES` constants); the field names they clear (`"dataset"`, `"features"`) are JSON keys and stay as they are.
  4. `ledger_rules.py` names the same milestones raw (`:98` `"dataset"`, `:118` and `:134` `"modeling"`), so use `DATASET` / `MODELING` there too (S-7).
  5. `ledger_ops.py` ends ≤ 170 lines, and `ledger_access.py` has 0 matches of the pattern too. Behaviour is unchanged: the whole datalab suite passes with no test edit except the new constant test.

### Fix Unit 3.2: One contract file for the ledger + card value sets, pinned on the Python side (REVIEW §3 row 1)
- **Files:** `packages/datalab/tests/test_ledger.py`, `contracts/README.md`
- **New files:** `contracts/value_sets.json`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** `contracts/mlflow_tags.json` + `test_tag_names_match_contract` (packages/datalab/tests/test_tracking.py:158) + `app/src/lib/tags.test.ts`.
- **HOW TO FIX:**
  1. Create `contracts/value_sets.json`: `{"schema_version": 1, "statuses": ["todo","produced","validated"], "decisions": ["validate","correct","redo"], "kinds": ["training","comparison"], "goals": ["max","min"]}`. Copy the order from the Python enums.
  2. In `test_ledger.py`, add `test_ledger_enums_match_contract`: `[s.value for s in Status] == contract["statuses"]`, and the same for `Decision` and `Kind` (lists, order included). (The `Goal` side is tested in 3.5.)
  3. Add one bullet to `contracts/README.md`: "`value_sets.json`: ledger statuses/decisions/kinds and the card metric goals. Compared with the Python enums (`test_ledger_enums_match_contract`, `test_goal_values_match_contract`) and the TS `as const` arrays (`ledger.test.ts`, `card.test.ts`)." Also fix the two stale "in Phase 5" mentions in that file if the app already reads the contract (check `app/src/lib/ledger.ts`, which imports `milestones.json`).

### Fix Unit 3.3: TS value sets pinned to the same contract (REVIEW §3 row 1, TS side; §3 row 5 `best.ts`)
- **Files:** `app/src/lib/ledger.test.ts`, `app/src/lib/card.ts`, `app/src/lib/card.test.ts`, `app/src/lib/best.ts`
- **Violation pattern (Grep):** `z\.enum\(\['max', 'min'\]\)|goal === 'max'`
- **Expected after fix:** 0 matches
- **Reference example:** `app/src/lib/tags.test.ts` (reads the contract with `readFileSync(new URL('../../../contracts/...', import.meta.url))`).
- **HOW TO FIX:**
  1. `ledger.test.ts`: `test('ledger value sets match contracts/value_sets.json', ...)` → `assert.deepEqual([...STATUSES], contract.statuses)`, and the same for `DECISIONS` and `KINDS`.
  2. `card.ts`: `export const GOALS = ['max', 'min'] as const; export type Goal = (typeof GOALS)[number];` and `goal: z.enum(GOALS)`. `card.test.ts`: `GOALS` deep-equals `contract.goals`.
  3. `best.ts:22`: replace the ternary with a typed map, `const SIGN: Record<Goal, number> = { max: -1, min: 1 };`, then `const sign = SIGN[metric.goal];`. A new `Goal` member then fails type-checking until it gets a sign.
  4. `npm run check && npm test` green.

### Fix Unit 3.4: A declarative milestone `TRANSITIONS` table, tested against the documented diagram (REVIEW §3 row 2)
- **Files:** `packages/datalab/src/datalab/ledger_model.py`, `packages/datalab/src/datalab/ledger_ops.py`, `packages/datalab/tests/test_ledger.py`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** target shape:
  ```python
  # (status before, decision) -> status after; `None` = produce. The ops consult it; ARCHITECTURE.md draws it.
  TRANSITIONS: Final[Mapping[tuple[Status, Decision | None], Status]] = {
      (Status.TODO, None): Status.PRODUCED,
      (Status.PRODUCED, None): Status.PRODUCED,
      (Status.PRODUCED, Decision.CORRECT): Status.PRODUCED,
      (Status.PRODUCED, Decision.VALIDATE): Status.VALIDATED,
      (Status.PRODUCED, Decision.REDO): Status.TODO,
  }
  ```
  Check each row against the current guards in `produce` / `decide` before writing it. `produce` refuses only VALIDATED today, so `(PRODUCED, None)` is legal; keep exactly today's behaviour.
- **HOW TO FIX:**
  1. **Red first.** `test_transitions_table_matches_ops`: for every `(status, decision)` pair in `Status × (Decision | None)`, build a ledger in that status, call the op, and assert that it succeeds iff the pair is in `TRANSITIONS` and ends in `TRANSITIONS[pair]`. Add `test_transitions_table_matches_architecture_md`: for each `TRANSITIONS` row, its rendered line (`todo + produce → produced`, …) appears verbatim in the table that ARCHITECTURE.md quotes (step 3). It is a string check, with no diagram parser (S-4).
  2. Add `TRANSITIONS` to `ledger_model.py`, and `def _next(status, decision) -> Status` in `ledger_ops.py`, which raises `LedgerError(f"{status} cannot take {decision or 'produce'}")` for a missing pair. `produce` and `decide` call `_next` instead of the inline status guards. The other guards (current milestone, winner, `redo_from` range) stay.
  2b. **`redo` is not a `TRANSITIONS` row.** `redo(lg, m)` resets m and every later milestone to TODO from **any** started status, VALIDATED included. It is a reset over a range of milestones, not a per-milestone move, and its guard is "m is the current milestone or an earlier one". Keep it as today's separate op, and do not run it through `_next`. The `(PRODUCED, REDO) → TODO` row covers only the *decision* `redo` on the current milestone, which `decide` then hands to `redo()`. The test in step 1 covers `redo()` separately: for each start status (TODO, PRODUCED, VALIDATED) of a started milestone, `redo` → TODO.
  3. `ARCHITECTURE.md` "Experiment milestone": add the `redo` edge to the diagram, and under it a 5-row table rendered from `TRANSITIONS` (one line per row, `before + decision → after`) as the section's code extract, plus one line under the table: "`redo(m)` (any started status, VALIDATED included) → TODO for m and every later milestone; a separate op, not a table row". Then say "Transitions: `datalab.ledger_model.TRANSITIONS`, checked against this table by `test_transitions_table_matches_architecture_md`".
  4. `ledger_ops.py` and `ledger_model.py` stay ≤ 200 lines.

### Fix Unit 3.5: Enums for the other repeated fixed sets (REVIEW §3 row 5, Python side)
- **Files:** `packages/datalab/src/datalab/project.py`, `packages/datalab/src/datalab/tracking_queries.py`, `projects/voice-arch/src/voice_arch/decide.py`, `projects/voice-arch/src/voice_arch/bench.py`, `templates/project/src/__DATALAB_PACKAGE__/train.py`, `packages/datalab/tests/test_project.py`
- **Violation pattern (Grep):** `Literal\["max", "min"\]|\("max", "min"\)|"RUNNING"|'RUNNING'|\("scored", "timeout", "agent_lost"\)|component == "|sub == "audit"|status == "FINISHED"`
- **Expected after fix:** 0 matches
- **Reference example:** `datalab.tags.Tag` (StrEnum + contract); `voice_arch.call.Outcome`; `mlflow.entities.RunStatus`.
- **HOW TO FIX:**
  1. `project.py`: `class Goal(StrEnum): MAX = "max"; MIN = "min"`. `CardMetric.goal: Goal`. In `card_metric`, `try: goal = Goal(raw)` / `except ValueError` → the same `ProjectError` text, built from `[g.value for g in Goal]`. Update the callers' comparisons (grep `\.goal ==`).
  2. `tracking_queries.py`: build the filter strings and the `!=` check from `RunStatus.to_string(RunStatus.RUNNING)` (one module constant `_RUNNING: Final = RunStatus.to_string(RunStatus.RUNNING)`).
  3. `decide.py:81`: `for o in (Outcome.SCORED, Outcome.TIMEOUT, Outcome.AGENT_LOST)` with `f"n_{o.value}"`.
  4. `bench.py`: `class Component(StrEnum): STT = "stt"; TTS = "tts"; LLM = "llm"`, with `--component` `type=Component, choices=list(Component)`, and `_dispatch` compares `is Component.STT` etc.
  5. Template `train.py`: `sub == AUDIT_EXPERIMENT` with a module constant `AUDIT_EXPERIMENT: Final = "audit"` (the reserved MLflow sub-experiment, also used by `eval.py`'s `sub="audit"`, so import it there too), and `r.info.status == RunStatus.to_string(RunStatus.FINISHED)`. `train.py` stays ≤ 200 lines.
  6. In `test_project.py`, add `test_goal_values_match_contract`: `[g.value for g in Goal] == value_sets["goals"]` (it reads `contracts/value_sets.json` from 3.2).
  7. All suites green.

### Fix Unit 3.6: Record the milestone-id typing decision (REVIEW §3 row 6; P-10 answered on 2026-11-08)
- **Files:** `decisions.md`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** the ADR format at the top of `decisions.md`.
- **HOW TO FIX:**
  1. ADR "Milestone ids stay data-driven strings" (user decision 2026-11-08, P-10). Context: the ids come from `contracts/milestones.json`, per kind. Decision: the ids the code names are `Final` constants (`MODELING`, `AUDIT`, `DATASET`, `FEATURES`, from 3.1), tested to exist in the contract; any other id is validated at runtime by `_require_current` / TS `superRefine` I-1. Alternatives considered: a generated `Literal` plus drift tests on both sides; won't fix. Add one sentence to ARCHITECTURE.md "Key Domain Concepts".

### Fix Unit 3.7: The platform skip cites its tracker (REVIEW §4 row 1, TQ6; §4 🔵 "platform-conditional")
- **Files:** `packages/datalab/tests/test_new_project.py`
- **Violation pattern (Grep):** `reason="needs a #!/bin/sh stub executable"`
- **Expected after fix:** 0 matches
- **Reference example:** the env-gated skips that cite #8 (`grep -rn "#8" packages/datalab/tests`).
- **HOW TO FIX:**
  1. `reason="platform-conditional (#8): the uv stub is a #!/bin/sh executable"`. Keep the test.
  2. Add the "platform-conditional" category to issue #8's body with `gh issue edit 8 --repo simonharel-simpro/data-lab --body-file <file>`: the existing body (read it first with `gh issue view 8`), plus a bullet "platform-conditional skips: a test whose fixture needs a POSIX feature (a `#!/bin/sh` stub) skips on Windows; CI runs on Linux".

### Fix Unit 3.8: `datalab.split` rejection tests name their rule; the seven untested rules are tested; one exhaustive property (REVIEW §4 row 3)
- **Files:** `packages/datalab/tests/test_split.py`
- **Violation pattern (Grep):** `pytest\.raises\(SplitError\):$`
- **Expected after fix:** 0 matches
- **Reference example:** `test_grouped_without_group_key_rejected` (`pytest.raises(SplitError, match="group_key")`). The rule texts live in `packages/datalab/src/datalab/split.py` (`_shape_problem`, `_overlap_problem`, `_time_problem`, the validators).
- **HOW TO FIX:**
  1. Add `match=` to the four bare `pytest.raises(SplitError):` (lines 73, 78, 89, 113), each with the exact text of the rule its input trips. Check that each input trips **one** rule only: prove it red with that rule commented out locally (do not commit that).
  2. A `@pytest.mark.parametrize("data, rule", [...], ids=[...])` test covering: a duplicate entry in one partition; mixed tz-aware/naive `time_max`; non-ISO `time_max`; time bounds with a non-temporal strategy; group bounds with a non-grouped strategy; an empty train; a negative index. Each case asserts `match=re.escape(rule)`. If a case is accepted today (no rule exists), stop and report it: that is a missing rule, not a test to weaken.
  3. **D-3**, the property by exhaustive enumeration (no new dependency): over the index set `range(4)`, enumerate every assignment of each index to `train` / `val` / `test` / none (4⁴ = 256 cases). Assert that `read_split` accepts it iff train and test are non-empty and that no index appears twice. Then, for each accepted split, copy one train member into test and assert `SplitError(match=<overlap rule>)`. Keep it under 1 s.

### Fix Unit 3.9: Assert the milestone sequences, not their lengths (REVIEW §4 row 4)
- **Files:** `packages/datalab/tests/test_ledger.py`
- **Violation pattern (Grep):** `\(9, 7\)`
- **Expected after fix:** 0 matches
- **Reference example:** —
- **HOW TO FIX:** in `test_contract_matches_kind_enum`, replace the length tuple with `assert sequences[Kind.TRAINING] == (<the 9 ids, in order>)` and the same for `COMPARISON` (7 ids). Copy the ids from `contracts/milestones.json` once, so the test pins the contract content and a reorder fails it.

## Verification

- `grep -nE '"(todo|produced|validated|validate|correct|modeling|audit)"' packages/datalab/src/datalab/ledger_ops.py packages/datalab/src/datalab/ledger_access.py` and `grep -nE '\["(dataset|modeling|audit|features)"\]' packages/datalab/src/datalab/ledger_rules.py` → 0 (the stricter check: no raw status/decision/milestone literal at all in the two op modules).
- The 3.5 pattern → 0 over its five files; the 3.3 pattern → 0 over `app/src/lib/card.ts` and `best.ts`.
- All Python suites + `npm run check && npm test` green. `/check`.

<!-- plan-validate: READY 2026-11-08 sha256:74ea4b368cb1 -->
