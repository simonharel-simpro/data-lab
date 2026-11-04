# Cross-side contracts

- Project name rule: `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`; reserved: `test, datalab, datalab-test, template, y, n, yes, no, on, off, true, false, null` (YAML 1.1 bool/null words: PyYAML and the JS parser disagree on them).
- The identical literal lives in `packages/datalab/src/datalab/project.py` (Python) and `app/src/lib/name.ts` (app).
- Both test suites read `name_vectors.json` (`accept` / `reject`), so drift between the two sides fails a test (F-12).
