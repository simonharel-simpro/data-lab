# Cross-side contracts

- Project name rule: `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`; reserved: `test, datalab, datalab-test, template, y, n, yes, no, on, off, true, false, null` (YAML 1.1 bool/null words: PyYAML and the JS parser disagree on them).
- The identical literal lives in `packages/datalab/src/datalab/project.py` (Python) and `app/src/lib/name.ts` (app).
- Both test suites read `name_vectors.json` (`accept` / `reject`), so drift between the two sides fails a test (F-12).
- `EXPERIMENT.md`: the kind-agnostic experiment contract (layout, ledger, split, test isolation, MLflow, budget). Read by people, the `/datalab:experiment` skill and both code sides.
- `milestones.json`: milestone ids, their agents, the three sequences (training, comparison, exploration) and `freeze_after`. Read by `datalab.ledger_model.contract()`; the app reads it in `app/src/lib/ledger.ts`.
- `run_ledger_vectors.json`: shared valid and invalid `run.json` cases with the first rule each breaks and `checked_by`. Read by `packages/datalab/tests/test_ledger.py` and, in Phase 5, the app tests.
- `mlflow_tags.json`: the 11 MLflow tag names. Compared with `datalab.tags.Tag` by `test_tag_names_match_contract` and, in Phase 5, with `app/src/lib/tags.ts`.
- Metric key rule: the identical `METRIC_KEY_RE` literal lives in `datalab.project` and `app/src/lib/card.ts`; `test_metric_key_re_matches_app_literal` compares the two strings.
- `value_sets.json`: ledger statuses/decisions/kinds and the card metric goals. Compared with the Python enums (`test_ledger_enums_match_contract`, `test_goal_values_match_contract`) and the TS `as const` arrays (`ledger.test.ts`, `card.test.ts`).
