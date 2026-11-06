# Implementation Plan — voice-arch (LiveKit voice-agent architecture experiment)

**Date:** 2026-11-06 · **Project:** `projects/voice-arch` (new, via `datalab-new`) · **Phases:** 3 · **Agent:** `python-fastapi`
**Source:** /think-with-me framing 2026-11-06 + planning-time measurements (below).

> ⚠️ Planned with review debt: 2 cycles un-reviewed (#17 openrouter-default, #19 weavit-web) — user override 2026-11-06.

## Goal

Pick the control architecture for a future Simpro phone agent (English, US formats, books a service appointment).
Priority when measures conflict: **task success > latency > cost**. Production bar: **≥ 90 % exact records** on messy
simulated personas and **median e2e latency < 1.2 s**. Budget **≤ 50 $**, all model calls through OpenRouter.
Stage 1 benchmarks STT / TTS / LLM on identical inputs; stage 2 compares three control architectures with the winners:
**A** orchestrator only · **B** orchestrator + state machine (LiveKit `TaskGroup`) · **C** B + side memory (call record).

## Planning-time measurements (OpenRouter, 2026-11-06)

| Component | Model | Result |
|---|---|---|
| STT (~9 s audio) | deepgram/nova-3 · assemblyai/universal-3-6-pro · openai/gpt-4o-mini-transcribe | 0.62 s · 1.08 s · 1.44 s |
| TTS TTFB (short line) | elevenlabs/eleven-flash-v2.5 · deepgram/aura-2 · deepgram/flux-tts | 0.68 s · 0.75 s · not measured |
| LLM TTFT + tool args | deepseek/deepseek-v4-flash · google/gemini-3.5-flash-lite · anthropic/claude-haiku-5.5 | 0.45 s 3/3 · 0.78 s 3/3 · 0.92 s 3/3 |

Sum per turn ≈ end-of-turn 0.5 + STT 0.6 + LLM 0.45 + TTS 0.7 ≈ **2.2 s**: the 1.2 s bar is expected to fail on
non-streaming OpenRouter audio. Then latency is reported comparatively and #25 tracks a direct streaming STT.

## Phase summary

| Phase | Title | Files (≈) | Depends on |
|---|---|---|---|
| 1 | Infra, gates, OpenRouter audio, normalisers + tool schemas, stage-1 bench, browser smoke | 26 | — |
| 2 | Booking domain + architectures A/B/C + worker | 16 | Phase 1 (settings, audio, normalisers, tool schemas) |
| 3 | Simulated caller, sweep runner, scoring, decision, human ratings, card | 14 | Phase 2 (worker, CallResult, record, calendar) |

Cross-phase contracts: Phase 1 produces `VoiceSettings`, `make_stt/make_tts/make_llm`, `key_usage()` / `SpendTracker`,
`normalize.py` (pure normalisers), `tool_schemas.py` (`TOOL_SCHEMAS`) and the chosen model defaults. Phase 2 produces `BookingRecord`, `CALENDAR`, `Arch` (`arch.py`), the worker (`agent_name=
"booking-agent"`) and `CallResult` sent on text-stream topic `voice-arch.result`. Phase 3 consumes all of it.

## Scope Analysis

| Feature | Layers / area | New | Modified |
|---|---|---|---|
| Infra + gates | compose, root env, hooks, CI | `infra/livekit.yaml`, project scaffold | `compose.yaml`, `.env.example`, `tests/test_compose.py`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `packages/datalab/tests/test_settings.py`, `ARCHITECTURE.md`, `decisions.md` |
| Stage-1 bench | settings, audio, bench, data | `settings.py`, `audio.py`, `openrouter_key.py`, `budget.py`, `booking/normalize.py`, `tool_schemas.py`, `fields.py`, `corpus.py`, `bench.py`, `winners.py`, `token.py`, `dispatch.py`, `smoke_agent.py`, `web/index.html`, `data/*` | `PROJECT.md` |
| Architectures | domain, agents, worker | `booking/{record,calendar,actions,instructions}.py`, `arch.py`, `agents/*`, `result.py`, `worker.py` | — |
| Experiment | caller, runner, scoring | `personas.py`, `caller.py`, `call_env.py`, `call.py`, `runner.py`, `scoring.py`, `naturalness.py`, `decide.py`, `rate.py`, `data/personas.jsonl` | `README.md`, `PROJECT.md` |

## Scope Decisions

| # | Type | What | Tracker | Approved |
|---|------|------|---------|----------|
| D-1 | decision | All STT/TTS/LLM calls through OpenRouter with the existing root key `OPENROUTER_API_KEY` (shared, 500 $ limit); a software experiment budget of 50 $ (`experiment_budget_usd`) stops the bench and sweeps; cost attribution assumes the key is not used elsewhere during a sweep (user choice 2026-11-06) | — | — |
| D-2 | decision | LiveKit server self-hosted in the data-lab compose, WebRTC only, every port on 127.0.0.1 | — | — |
| D-3 | decision | Booking agent = LiveKit worker on the host; simulated caller = AgentSession hosted in the runner on a self-connected room | — | — |
| D-4 | decision | Audio via LiveKit `openai` plugins with `base_url` = OpenRouter; one thin adapter only if the phase-1 spike fails | — | — |
| D-5 | decision | Architecture B = LiveKit `TaskGroup` (beta); per-field instructions shared by A, B and C | — | — |
| D-6 | decision | Latency = LiveKit `e2e_latency` from the session report; cost = OpenRouter `GET /api/v1/key` usage delta per sweep | — | — |
| D-7 | decision | Worker → runner result over a LiveKit text stream (topic `voice-arch.result`), no shared files | — | — |
| D-8 | decision | US phone/address formats; problem types plumbing / electrical / hvac / appliance / other | — | — |
| D-9 | decision | One MLflow run per sweep (per arch, per bench component); only full arch sweeps log `exact_rate` | — | — |
| D-15 | decision | Winner rule: `exact_rate` tie within 2 calls of 30 → latency p50 → cost; none ≥ 90 % → ranked and flagged "none production-ready"; human rating informative only | — | — |
| D-16 | decision | One OpenRouter key: `cost_usd` and `cost_per_call_usd` include the simulated caller's spend (labelled as such) | — | — |
| D-17 | decision | Simulated caller LLM fixed to `google/gemini-3.5-flash-lite` at temperature 0.7, distinct from the agent's model; both logged | — | — |
| D-18 | decision | Static enumerated calendar (12 slots, booked flags in code); booked slots refused | — | — |
| D-19 | decision | LiveKit service under compose profile `voice` (the default stack needs no LiveKit keys) | — | — |
| D-10 | defer | Speech-to-speech architecture (phase 2 of the experiment) | #21 | — |
| D-11 | defer | SIP / real telephony and 8 kHz audio realism | #22 | — |
| D-12 | defer | French-language agent | #23 | — |
| D-13 | defer | Real Simpro APIs, RAG, customer history | #24 | — |
| D-14 | defer | Direct streaming STT if the 1.2 s bar fails | #25 | — |

## Existing Equivalents

| Mechanism | Existing code (path:line @ main) | Plan |
|---|---|---|
| Project scaffold + `uv lock` | `packages/datalab/src/datalab/new_project.py` (`datalab-new`) | reuse |
| `DATALAB_*` infra settings | `packages/datalab/src/datalab/settings.py:13` | reuse, unchanged |
| MLflow preflight + `tracked_run` (`project` tag, bounded retries, FAILED on exception) | `packages/datalab/src/datalab/tracking.py:35,57` | reuse |
| Project settings, SecretStr, startup validation, `hide_input_in_errors` | `projects/mini-rag/src/mini_rag/settings.py` | copy the pattern (`VOICE_ARCH_*`) |
| OpenRouter provider allow-list | `projects/mini-rag/src/mini_rag/generate.py` | replaced by `openai.LLM.with_openrouter(provider=…)` |
| Per-item JSONL crash copy, metrics once, `smoke_*` for subsets | `projects/mini-rag/src/mini_rag/run.py:64-110` | copy |
| Normalised containment | `projects/mini-rag/src/mini_rag/scoring.py:56-69` | copy (~25 lines) into `booking/normalize.py` |
| Calendar fake + scenario personas | livekit/agents examples `FakeCalendar`, `scenarios.yaml` (MIT) | shape only: 12 slots enumerated in code (D-18), scenario-style personas |
| 127.0.0.1-only pinned compose service | `compose.yaml` | add `livekit` |
| App card metric | `app/src/lib/mlflow.ts:59-81` (max of `metric.key` over finished runs) | `metric: {key: exact_rate, goal: max}` |

## Simplicity Review

Before → after: 5 phases → 3 · ~14 modules → ~9 · 91 MLflow runs → 3 + bench (reviewer: fable, 2026-11-06)

| # | Action | Class | What | Disposition |
|---|--------|-------|------|-------------|
| S-1 | simplify | mechanism | One audio client: LiveKit openai plugins for bench and stage 2 | applied (D-4) |
| S-2 | simplify | mechanism | `e2e_latency` from the session report, no caller instrumentation | applied (D-6) |
| S-3 | simplify | mechanism | Cost from `/api/v1/key` usage delta, no `cost.py`; budget enforced in software over the shared key (`budget.py`) | applied (D-1, D-6) |
| S-4 | simplify | mechanism | One MLflow run per sweep; drop summary run and `report.py` | applied (D-9); naturalness counters kept by user |
| S-5 | simplify | mechanism | B = `TaskGroup` built-ins, no hand-written FSM | applied (D-5) |
| S-6 | simplify | mechanism | `with_openrouter(provider=…)` instead of copied routing | applied |
| S-7 | simplify | mechanism | Static calendar + scenario personas from LiveKit examples | applied (D-18) |
| S-8 | simplify | mechanism | One `bench.py`; constants for candidates; no JSON handoff | applied |
| S-9 | simplify | mechanism | Caller hosted in the runner, not a 2nd worker | applied (D-3) |
| S-10 | add | — | Windows-browser media smoke + rtc config | applied, Phase 1 |
| S-11 | add | — | LLM-backed tests marked `integration` | applied, Phases 2-3 |
| S-12 | add | — | Gates, CI job, G-10 parity, ADR for the new tree | applied, Phase 1 |
| S-13 | keep | — | Own simulated caller (`lk agent simulate` needs LiveKit Cloud) | kept |

## Mechanical Rules to Enforce

| Rule | Apply at phase | Recipe match | Scaffold command |
|------|---------------|--------------|------------------|
| `src/` modules ≤ 200 lines | Phase 1 | existing hook `tools/check_file_size.py` (covers every `projects/*/src`) | none — verify it matches the new tree |
| Every `voice_arch` import is a declared dependency | Phase 1 | existing `tools/pre_commit_checks/check_declared_dependencies.py` | add hook `declared-deps-voice-arch` (mirror `declared-deps-mini-rag`) |

No new linter: the other rules of this release (no fallback arch, only full sweeps log `exact_rate`) are semantic and
covered by tests (F-9, U-6).

## CI Gate Surface

| Gate | Laid by | At phase |
|------|---------|----------|
| Hook runner, ruff, gitleaks, file size, CI-parity workflow | existing data-lab surface | already present |
| `voice-arch` tree: declared deps, lint-imports + pyright + pytest `--cov` (floor 70) pre-push hook, CI job `voice-arch` (`uv sync --locked`, pip-audit) | Phase 1 | Phase 1 (first phase creating `src/` + tests) |

Verification at release: `/loop-implement` Step 10 runs `recipes/ci/gate-inventory/ci_gate_inventory.py`.

## Failure Modes (resilience)

Trust boundaries crossed: network (OpenRouter, LiveKit), subprocess/concurrency (worker + runner + caller), config, MLflow.

| # | Failure mode | Dimension | Required handling | Required test | Phase |
|---|---|---|---|---|---|
| F-1 | Call never ends | concurrency | agent ends session after `confirm_booking`; caller stop rule; runner per-call deadline → delete room, `outcome=timeout` | `test_f_1_runner_times_out_a_call_whose_caller_never_hangs_up` | 3 |
| F-2 | Booking agent never joins / dies | external | runner watches the caller's room: no agent within `agent_join_timeout_s` → abort sweep; disconnect mid-call → `outcome=agent_lost` | `test_f_2_sweep_aborts_when_no_agent_joins_within_deadline` | 3 |
| F-3 | Result handoff lost | partial-failure | self-inflicted → design changed: text stream instead of files (D-7); worker sends an error `CallResult` when the report can't be built; no result before the deadline = failure | `test_f_3_missing_result_scores_as_failure` | 2, 3 |
| F-4b | Experiment budget reached | money | bench and sweep refuse to start when `spent_so_far + estimate >= experiment_budget_usd`; a sweep re-reads key usage after each call and stops (`BudgetExceeded`, run FAILED, rows kept) once spent reaches the budget; `cost_usd` is logged on every run, failed ones included | `test_budget_exceeded_mid_sweep_stops_before_next_call`, `test_bench_refuses_when_budget_spent`, `test_spend_tracker_reports_cost_on_exception` | 1, 3 |
| F-4 | OpenRouter 401/402 mid-sweep | auth | `CallResult.http_status` 401/402 (either side) aborts the sweep and the bench, run FAILED, no further rooms; takes precedence over `caller_fault` | `test_f_4_402_aborts_sweep_and_creates_no_further_rooms` | 1, 3 |
| F-5 | Failures dropped from the denominator | observability | every planned call yields a row with `outcome`; non-scored = not exact; counters per outcome | `test_f_5_timeouts_and_errors_count_as_misses_in_exact_rate` | 3 |
| F-6 | Caller fault blamed on the arch | observability | `outcome=caller_fault` excluded from arch metrics, counted; > 10 % of calls → run FAILED | `test_f_6_caller_error_close_is_classified_caller_fault` | 3 |
| F-7 | `e2e_latency` missing | state | `.get()`; count `latency_turns_missing`; empty → metric absent, never 0 | `test_f_7_latency_aggregation_tolerates_missing_and_all_missing_e2e` | 3 |
| F-8 | Both agents talk at t=0 | concurrency | only the booking agent greets; caller waits for the first agent turn | `test_f_8_caller_does_not_speak_before_first_agent_turn` | 3 |
| F-9 | Bad dispatch metadata | input | unknown `arch` refused with an error result, never defaulted to A | `test_f_9_unknown_arch_metadata_is_refused_not_defaulted` | 2 |
| F-10 | Empty/garbage STT body | external | spike asserts non-empty; bench counts empty transcript as an error | `test_f_10_empty_transcript_counts_as_stt_error_in_bench` | 1 |
| F-11 | WAV cache partial or stale | partial-failure | tmp + rename; manifest hash covers files + TTS model + voice; mismatch → rebuild | `test_f_11_truncated_or_other_voice_cache_is_rejected` | 1 |
| F-12 | `/api/v1/key` read fails | external | `SpendTracker` never raises: a failed read → cost absent + warning, run not failed; `key_usage` on a wrong shape raises, never returns 0 | `test_f_12_key_usage_read_failure_omits_cost_without_failing_run` | 1, 3 |
| F-13 | WSL2 browser media | cross-platform | smoke checks audio both ways, records UDP vs TCP | manual (README runbook) | 1 |
| F-14 | Retries inflate latency | observability | log session error/retry counts as metrics | `test_f_14_session_errors_are_counted` | 3 |
| F-15 | TaskGroup summarisation adds an LLM call | state | set `summarize_chat_ctx=False` explicitly, logged as param | `test_f_15_taskgroup_summarize_flag_is_off_and_logged` | 2 |
| F-16 | Turn/interruption detection differs dev vs start, may call LiveKit Cloud | cross-platform | every session pins `turn_handling` VAD; worker `max_tool_steps=6`; both logged | `test_f_16_turn_handling_and_tool_steps_are_pinned` | 2, 3 |
| F-17 | Caller session ignores AGENT-kind participants | external | caller `room_options.participant_kinds=[AGENT]` | `test_one_live_call_produces_a_row` (integration) | 3 |

Each mode above is a phase acceptance criterion: its handling AND its test ship in the named phase.

## Unspecified Behaviors (spec-gap)

Decision points: scoring, aggregation, winner selection, naturalness counters, card metric.

| # | Behavior (was unstated) | Decided resolution | Required test | Phase |
|---|---|---|---|---|
| U-1 | Full sweep | 6 personas × 5 reps (`FULL_REPS = 5`, logged); fewer → `smoke_*` only | `test_u_1_sweep_with_fewer_reps_than_full_logs_smoke_metrics_only` | 3 |
| U-2 | Exact record | 5 fields equal after normalisation AND `confirmed`; any `record_*` after confirm resets `confirmed` | `test_u_2_record_edit_after_confirm_resets_confirmed`, `test_u_2_unconfirmed_correct_record_is_not_exact` | 2, 3 |
| U-3 | Timeout / crash | agent-side → not exact, in denominator; caller-side → `caller_fault` (F-6); infra → abort (F-2) | `test_u_3_agent_timeout_counts_as_not_exact_in_denominator` | 3 |
| U-4 | US phone / address | phone: spoken digits mapped, digits only, a leading `1` dropped from 11 digits → 10 digits; address: casefold, abbreviation map, equality on number + street + city + state (ZIP optional) | `test_u_4_phone_spoken_double_and_oh_normalise_to_digits` + address table | 2 |
| U-5 | Problem type | `ProblemType` = plumbing/electrical/hvac/appliance/other; first stated problem wins; each persona fixes its expected value | `test_u_5_persona_expected_problem_type_is_valid_enum` | 2, 3 |
| U-6 | Card metric | only full arch sweeps log `exact_rate`; bench logs `stt_*`/`tts_*`/`llm_*`; `rate.py` logs `human_rating` only | `test_u_6_bench_never_logs_exact_rate`, `test_u_6_rating_run_never_logs_exact_rate` | 1, 3 |
| U-7 | Calendar date | frozen `REFERENCE_DATE = 2026-11-09` (Monday); persona expected slots must exist | `test_u_7_persona_expected_slot_exists_in_calendar` | 2, 3 |
| U-8 | Name equality | NFKC + casefold + collapse spaces + drop `'` and `.`; exact equality | `test_u_8_smyth_does_not_match_smith` | 2 |
| U-9 | Stage-1 winners | STT: fewest field errors, ±1 error per 40 = tie → lower p50 latency (cost reported, not ranked); TTS: round-trip intelligibility gate then TTFB; LLM: tool-arg accuracy then TTFT | `test_u_9_accuracy_within_margin_falls_back_to_latency` | 1 |
| U-10 | Latency aggregation | pool non-None turns across calls; `statistics.quantiles(method="inclusive")`; log turn counts | `test_u_10_no_turns_omits_latency_metrics` | 3 |
| U-11 | Long silence | agent-owed gap (user stopped → agent started) strictly > 2.0 s; caller think-time excluded | `test_u_11_exactly_two_seconds_is_not_long` | 3 |
| U-12 | Handled barge-in | interrupted agent message followed by an agent reply that is not a normalised near-duplicate of it | `test_u_12_verbatim_repeat_after_interrupt_is_not_handled` | 3 |
| U-13 | Per-field denominator | missing field = wrong; denominator = all scored + agent-failed calls | `test_u_13_missing_field_counts_as_incorrect` | 3 |
| U-14 | Card tie | keep the card's tie rule; the arch decision comes from `pick_arch` (D-15), restated in PROJECT.md | none (docs) | 3 |
| U-15 | LLM tool-arg accuracy (bench) | compare args per field after `normalize_phone/address/name`; problem/slot exact | `test_u_15_llm_arg_accuracy_compares_normalised_values` | 1 |
| U-16 | Architecture decision | `pick_arch(metrics)` implements D-15 | `test_u_16_arch_within_exact_margin_falls_back_to_latency`, `test_u_16_no_arch_meets_bar_still_ranks_and_flags` | 3 |
| U-17 | Booked slot | `choose_slot` on a booked slot → error string, record unchanged; personas must expect a free slot | `test_u_17_choose_booked_slot_returns_error_and_keeps_record`, `test_u_17_persona_expected_slot_is_free` | 2, 3 |
| U-18 | slot_change persona | changes the slot during the agent's read-back, before saying yes; the agent updates and re-reads; session ends after confirm | `test_u_18_slot_change_during_readback_reconfirms_new_slot` (integration) | 2, 3 |
| U-19 | Cost per call | `cost_per_call_usd = cost_usd / (scored + timeout + agent_lost)`, caller spend included (D-16) | `test_u_19_cost_per_call_uses_exact_rate_denominator` | 3 |
| U-20 | Caller variance | caller model + temperature from settings (D-17), logged | `test_u_20_caller_llm_uses_configured_model_and_temperature` | 3 |
| U-21 | Budget before a sweep | superseded by F-4b (the shared key's `limit_remaining` says nothing about the 50 $ experiment budget) | — (see F-4b tests) | 3 |
| U-22 | Stage-1 edge cases | no intelligible TTS → `NoEligibleCandidate`, defaults kept, run tagged; STT margin measured from the best | `test_u_22_pick_tts_with_no_intelligible_candidate_raises`, `test_u_22_stt_margin_is_measured_from_the_best` | 1 |
| U-23 | Human ratings | mean per arch, ≥ 1 call per arch, not blind | `test_u_23_human_ratings_aggregate_by_mean_per_arch` | 3 |
| U-24 | Spelled names | runs of single letters separated by `-`/spaces are joined before name normalisation | `test_u_24_spelled_letters_normalise_to_joined_name` | 1 |
| U-25 | Scored fields drift | one `SCORED_FIELDS` constant; persona `expected_record` typed with `extra="forbid"` | `test_u_25_expected_record_keys_equal_scored_fields` | 2, 3 |
| U-26 | Bench cases vs tools | `data/llm_cases.jsonl` tool names/arg keys = `TOOL_SCHEMAS` (Phase 1), reused by Phase 2 tools | `test_u_26_llm_cases_match_tool_schemas` | 1, 2 |

Bench audio is synthesised with a TTS from a vendor that is not an STT candidate (google/gemini-3.8-flash-lite-tts),
logged as a param, to avoid favouring one STT.
