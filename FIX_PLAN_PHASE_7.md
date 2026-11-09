# Fix Plan — Phase 7: Docs & dependency hygiene

**Status:** ✅ Complete — branch fix-phase-7-docs-deps-hygiene, 2026-11-09
**Severity:** 🟡
**Agent:** general-purpose. 7.1 is docs plus one import-linter contract (run `cd projects/voice-arch && uv run --locked lint-imports` after it). 7.2 edits `pyproject.toml` + `uv.lock` (run `uv lock` and every tree's gates after it).
**Depends on:** Phases 3 and 4 (the docs describe `ledger_access`, `TRANSITIONS`, `load_settings`, the regrouped signatures)
**Fix units:** 2
**Files affected:** 6

## Within-phase Dependencies

All fix units in this phase are independent. P-8 and P-9 were answered by the user on 2026-11-08.

## Fix Units

### Fix Unit 7.1: ARCHITECTURE.md matches the code (REVIEW §1 rows 3–4, §3 row 4, §5 rows 4–5, §2 row 5)
- **Files:** `ARCHITECTURE.md`, `projects/voice-arch/pyproject.toml`, `decisions.md`, `README.md`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches
- **Reference example:** the existing "Shared package" layer block (ARCHITECTURE.md:92-100): Does / Must NOT / Modules / code extract.
- **HOW TO FIX:**
  1. **Shared package (§1 row 3).** Make the "Modules:" list complete: `project`, `settings`, `tracking`, `tracking_queries`, `new_project`, `ledger` (facade), `ledger_model`, `ledger_rules`, `ledger_ops`, `ledger_access`, `ledger_checks`, `split`, `tags`, `wiring`, `wiring_parity`. Mark which are pure: copy the import-linter list in `packages/datalab/pyproject.toml` (~lines 38-52). Extend "Does:" with the experiment ledger, the frozen split and the hook wiring.
  2. **voice-arch layers (§1 row 4 + §1 🔵 `sweep_query`).** Add a module → layer table under "Voice architectures" / "Voice sweeps", covering every module in `projects/voice-arch/src/voice_arch/`, as measured on 2026-11-08 by `grep -lE '^(import|from) (mlflow|datalab|httpx|livekit)'`:
     - **pure** (none of those imports): `arch`, `call`, `call_env`, `candidates`, `fields`, `naturalness`, `personas`, `result`, `scoring`, `sweep_log`, `winners`, plus the `booking` package;
     - **MLflow / runs**: `bench`, `bench_record`, `budget`, `decide` (imports `mlflow`, so it is **not** pure), `rate`, `runner`, `sweep_query`;
     - **IO adapters / LiveKit**: `audio`, `caller`, `corpus`, `dispatch`, `live_caller`, `livekit_env`, `llm_dump`, `llm_guard`, `openrouter_key`, `seams`, `settings`, `token`, `tool_schemas`, `worker_logic`, the `agents` package;
     - **entry points**: `worker`, `smoke_agent` (and the `main()` of `runner` / `bench`).
     Re-run the grep after Phases 1–4 and update the lists (e.g. 1.4 may add `sweep.py`). Then change `projects/voice-arch/pyproject.toml` **exactly** as follows. (a) In the existing contract "scoring and decision stay LiveKit-free", remove `"voice_arch.sweep_query"` from `source_modules` (it stays LiveKit-free in practice, but it is a runs module). Keep `decide` there: it is LiveKit-free. (b) Add a new contract after it:
     ```toml
     [[tool.importlinter.contracts]]
     name = "pure modules stay MLflow-free"
     type = "forbidden"
     source_modules = [
         "voice_arch.arch", "voice_arch.call", "voice_arch.call_env", "voice_arch.candidates", "voice_arch.fields",
         "voice_arch.naturalness", "voice_arch.personas", "voice_arch.result", "voice_arch.scoring",
         "voice_arch.sweep_log", "voice_arch.winners",
     ]
     forbidden_modules = ["mlflow", "datalab", "httpx", "livekit"]
     ```
     The list must equal the table's **pure** row. Verify with the grep above that none of them imports a forbidden module, then run `uv run --locked lint-imports`, which must pass. If a module listed as pure fails, move it to its real row in both the table and the contract. Never add an `ignore_imports` to make it pass.
  3. **`.claude/` (§5 row 4).** In Project Structure, add `.claude/skills/experiment/` (the `/experiment` skill: `SKILL.md`, `references/agent-overrides.md`, `references/dispatch-briefs.md`, pointing to `contracts/EXPERIMENT.md`) and `.claude/hooks/` (loop guards, statusline). Add a one-line pointer in `README.md`.
  4. **Grace period (§5 row 5).** Infra layer: "`stop_grace_period: 60s` on Weaviate (#36) lets it flush the HNSW commit log on an orderly stop. A hard kill (`wsl --shutdown`, a Docker Desktop restart, OOM) can still lose it; mini-rag's reuse check probes vector search for that reason (Phase 1.1)."
  5. **Card status (§3 row 4, D-5).** Under "### Project `status` (card frontmatter)": "The status is a hand-edited label. The diagram is the intended workflow, and nothing enforces the transitions. The app only checks that the value is one of `STATUSES` and that the required sections for that status are present (`app/src/lib/completeness.ts`)."
  6. **`from __future__` (§2 row 5; P-8, user 2026-11-08).** Add a line under the Python conventions: "py312+: `from __future__ import annotations` is not required; PEP 604/585 syntax is native and ruff `UP` keeps it modern". Add a short ADR in `decisions.md`.

### Fix Unit 7.2: Dev dependency specs stay `>=`, recorded (REVIEW §5 row 3; P-9 = A, D-7, #40)
- **Files:** `decisions.md`, `packages/datalab/pyproject.toml`, `projects/mini-rag/pyproject.toml`, `projects/voice-arch/pyproject.toml`
- **Violation pattern (Grep):** `N/A`
- **Expected after fix:** 0 matches (no code change: the 12 `>=` dev specs stay, accepted by the user on 2026-11-08, #40)
- **Reference example:** the ADR format in `decisions.md`.
- **HOW TO FIX:**
  1. Do not change the `pyproject.toml` files.
  2. ADR "Dev dependency specs stay `>=`; `uv.lock` + `uv sync --locked` is the pin". Context: REVIEW 2026-11-04 and 2026-11-08 flag the specs. The user decided this on 2026-11-04 and confirmed it on 2026-11-08 (P-9). Tracker: #40. Alternative considered: `==` like voice-arch's other dev pins. Consequence: `uv lock --upgrade` keeps working.

## Verification

- `uv run --locked lint-imports` green in voice-arch; every tree's gates green after 7.2.
- The 12 `>=` dev specs are unchanged and the ADR cites #40; ARCHITECTURE.md names every `voice_arch` module (`ls projects/voice-arch/src/voice_arch/*.py | xargs -n1 basename | sed 's/\.py$//'`, each found in ARCHITECTURE.md).
- `/check`.

<!-- plan-validate: READY 2026-11-08 sha256:3c5404d2fe06 -->
