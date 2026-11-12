# Fix Plan — Phase 3: App & CI gates

**Severity:** 🟡
**Agent:** general-purpose
**Depends on:** Phase 2 (2.2 and 2.4b also edit `.pre-commit-config.yaml`; land them first to avoid conflicts)
**Fix units:** 3
**Files affected:** 6

Context: hook runner `.pre-commit-config.yaml` (authoritative gate: `pre-commit run --all-files --hook-stage pre-push`); CI `.github/workflows/ci.yml`; tracked waivers and declared trees in `.ci-gate-exemptions.json`, read by `~/.claude/recipes/ci/gate-inventory/ci_gate_inventory.py` (schema in that folder's `README.md`: `"trees": [{"path", "stack", "reason"}]`). The Astro app lives in `app/` (npm, `output: 'static'`) and needs node ≥ 22.22 on PATH (`nvm use`).

## Within-phase Dependencies

3.2 and 3.3 both edit `ARCHITECTURE.md`: run 3.2 before 3.3. 3.1 is independent.

## Fix Units

### Fix Unit 3.1: Declare the five Python trees for the gate inventory
- **Files:** `.ci-gate-exemptions.json`
- **Violation pattern (Grep):** N/A
- **Expected after fix:** 0 matches
- **Done when:** `python3 ~/.claude/recipes/ci/gate-inventory/ci_gate_inventory.py --root .` lists six trees (`.`, `packages/datalab`, `projects/mini-rag`, `projects/voice-arch`, `templates/project`, `app`) and exits 0; paste its table into the PR.
- **Reference example:** `~/.claude/recipes/ci/gate-inventory/README.md` (`"trees": [{"path": ".", "stack": "python", "reason": "…"}]`).
- **HOW TO FIX:**
  1. Add a top-level `"trees"` array (after `"gate_tools"`) with five objects, each `"stack": "python"`: `{"path": ".", "reason": "root tools/ + tests/: no manifest by design (ADR 3)"}`, and `packages/datalab`, `projects/mini-rag`, `projects/voice-arch`, `templates/project` each with `"reason": "manifest at depth 2, below the inventory's depth-0/1 detection"`.

### Fix Unit 3.2: Pre-push builds the app once
- **Files:** `.pre-commit-config.yaml`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `npm run check && npm test'`
- **Expected after fix:** 0 matches
- **Done when:** `pre-commit run gates-app --all-files --hook-stage pre-push` passes with MLflow stopped (the CI build job has no MLflow service either, so the build must not need it).
- **Reference example:** `ci.yml` step "build with the real projects/ (zero projects is valid, F-15)" → `npm run build`.
- **HOW TO FIX:**
  1. Change the end of the `gates-app` entry from `npm run check && npm test'` to `npm run check && npm test && npm run build'` (the real-projects build; the four fixture builds stay CI-only — they repoint env vars at fixture folders and two of them must fail). Rename the hook to "app lint + format check + astro check + unit tests + coverage floor + build".
  2. `ARCHITECTURE.md`: wherever the `gates-app` hook command is described (grep `gates-app` and `npm run check`), add `npm run build`.

### Fix Unit 3.3: JS SAST for the app, enforced
- **Files:** `app/eslint.config.js`, `app/package.json`, `app/package-lock.json`, `app/src/lib/name.ts`, `ARCHITECTURE.md`
- **Violation pattern (Grep):** `"lint": "eslint \.",`
- **Expected after fix:** 0 matches
- **Done when:** `cd app && npm run lint` exits 0 with `--max-warnings 0` in effect, it exits non-zero when one of the inline disables is removed temporarily (then restored), and `npm audit --audit-level=moderate` exits 0.
- **Reference example:** the existing flat-config entries in `app/eslint.config.js` (e.g. `eslint-plugin-astro`).
- **HOW TO FIX:**
  1. `cd app && npm install --save-dev --save-exact eslint-plugin-security@4.2.0` (4.2.1 is under two weeks old).
  2. `app/package.json`: `"lint": "eslint . --max-warnings 0"` — the plugin's recommended rules are warnings, so without this the gate can never fail (measured: 13 warnings, exit 0).
  3. `eslint.config.js`: `import pluginSecurity from 'eslint-plugin-security';`, add `pluginSecurity.configs.recommended` to the exported array, then add one override object after it:
     ```js
     {
       // build-time code: reads repo files and indexes repo data, never user input
       files: ['src/lib/**'],
       rules: { 'security/detect-non-literal-fs-filename': 'off', 'security/detect-object-injection': 'off' },
     },
     ```
  4. `app/src/lib/name.ts:2` (`NAME_RE`, `security/detect-unsafe-regex`): add above it `// eslint-disable-next-line security/detect-unsafe-regex -- anchored; each repetition starts with a literal '-', so matching is linear; literal mirrored from datalab project.py`.
  5. Run `npm run lint`. If any other `security/*` warning remains (any rule, any file), STOP and report rule, file and line — do not suppress it.
  6. `ARCHITECTURE.md` (after 3.2): where the app's lint tooling is described (grep `eslint`), add "`eslint-plugin-security` (recommended), warnings fail the lint (`--max-warnings 0`)".

## Verification

Run `pre-commit run --all-files --hook-stage pre-push`, the inventory command from 3.1, then `/check`.

<!-- plan-validate: READY 2026-11-11 sha256:14859f99f498 -->
