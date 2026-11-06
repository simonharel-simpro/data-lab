# Phase 3 — Simulated caller, sweep runner, scoring, human ratings, card

**Depends on Phase 2:** `BookingRecord`, `is_exact`, `normalize_*`, `CALENDAR`, `ProblemType`
(`src/voice_arch/booking/`), `Arch` / `parse_arch` (`agents/registry.py`), `CallResult` + `RESULT_TOPIC =
"voice-arch.result"` (`result.py`), the worker registered as `agent_name="booking-agent"` (dispatch metadata
`{"arch": "a|b|c", "run_id": "…"}`, sends one `CallResult` JSON on the text-stream topic, then leaves).
**Depends on Phase 1:** `VoiceSettings`, `make_stt / make_tts / make_llm`, `SpendTracker` (`openrouter_key.py`), datalab
`tracked_run` / `preflight`. **Agent:** `python-fastapi`.

Context (self-contained): a sweep runs one architecture against 6 messy personas × 5 reps. The simulated caller is an
`AgentSession` hosted inside the runner process on a self-connected `rtc.Room` (token from `livekit-api`); it uses the same
STT/TTS models as the agent and the LLM from settings. Results are scored against each persona's expected record. Priority
for the final decision: task success > latency > cost. Budget: the OpenRouter key has a 50 $ credit limit (402 = stop).

## Data

#### `data/personas.jsonl` (NEW, 6 lines)
`{"id", "behaviour", "instructions", "expected_record": {"name","phone","address","problem_type","slot_id"}}`. US formats.
Personas: `self_correction` (gives a phone, corrects one digit), `out_of_order` (address before name, problem first),
`interrupter` (talks over the agent's read-back), `slot_change` (accepts a slot, then changes it after confirmation is
asked), `speller` (unusual name, spells it: e.g. Siobhan Smyth), `vague_problem` ("the water's acting weird" →
expected `plumbing`). Instructions tell the caller to answer naturally, never invent fields beyond its record, and hang up
after the agent's goodbye. Expected `slot_id`s are real `CALENDAR` ids.

## Source

#### `src/voice_arch/personas.py`
`Persona` (pydantic) + `load_personas(path) -> list[Persona]`: `expected_record.problem_type` must be a `ProblemType`
(U-5), `slot_id` must exist in `CALENDAR` (U-7), ids unique, exactly the 6 expected behaviours. Errors →
`PersonaError` naming the line.

#### `src/voice_arch/caller.py`
`CallerAgent(Agent)`: instructions = persona instructions + "Wait for the agent to speak first" (F-8) + "When the agent
says goodbye, say bye and stop". No `on_enter` greeting. `caller_session(settings, persona) -> AgentSession` (STT via
StreamAdapter + VAD, TTS, LLM from Phase-1 factories). Stop rule: after the agent's goodbye or `max_caller_turns = 20`.

#### `src/voice_arch/runner.py` (CLI `python -m voice_arch.runner --arch a|b|c [--personas id,...] [--reps N]`)
**Purpose:** one sweep = one MLflow run (D-9). Flow:
1. `VoiceSettings()`, datalab `Settings()`, `preflight()`, `load_personas()` — all before any I/O to LiveKit (F-13).
2. `with SpendTracker(...)` and `tracked_run(project, settings, run_name=f"arch-{arch}", sub="conversations")`.
3. For each persona × rep: room name `va-{run_id[:8]}-{arch}-{persona}-{rep}-{uuid4().hex[:6]}`; create the dispatch
   (`livekit-api`, metadata arch + run_id); connect the caller room; register a text-stream handler for `RESULT_TOPIC`;
   start the caller session.
   - No `booking-agent` participant within `agent_join_timeout_s` → abort the sweep, run FAILED (F-2).
   - Agent participant disconnects before a result arrives → `outcome=agent_lost`.
   - No result within `call_timeout_s` → delete the room, `outcome=timeout` (F-1).
   - Result `close_reason`/`error` showing HTTP 401/402 (either side) → abort the sweep, run FAILED (F-4).
   - Caller session error (its STT/TTS/LLM) → `outcome=caller_fault` (F-6).
   - Otherwise `outcome=scored`.
   Append one row per call to `results/<run_id>.jsonl` at once (crash copy): persona, rep, outcome, record, per_field,
   exact, latency rows, naturalness counters, error/retry counts.
4. Aggregate with `scoring.aggregate(rows, full=…)` and log metrics once; params: arch, models (stt/tts/llm/voice),
   provider allow-list, reps, personas, `FULL_REPS`, timeouts, `summarize_chat_ctx`; artifact `per_conversation.json`;
   `cost_usd` from `SpendTracker` (absent if the read failed, F-12).
5. `caller_fault` > 10 % of calls → raise after logging the rows, run FAILED (F-6).

#### `src/voice_arch/scoring.py`
**Purpose:** pure aggregation. `FULL_REPS = 5`; `ALL_PERSONAS = 6`.
`aggregate(rows, *, full: bool) -> dict[str, float]` (keys prefixed `smoke_` when not full, U-1):
- `exact_rate` = exact / (scored + timeout + agent_lost) — failures stay in the denominator (F-5, U-3); `caller_fault`
  excluded (F-6). `n_<outcome>` counters for every outcome.
- per-field accuracy `field_<name>_acc` with the same denominator, a missing field wrong (U-13).
- latency: pool every turn's `e2e_latency` that is not None across calls; `latency_p50_s`, `latency_p90_s` via
  `statistics.quantiles(n=10, method="inclusive")`; `latency_turns`, `latency_turns_missing`; no p50/p90 key when there is
  no turn (U-10, F-7).
- `barge_ins`, `barge_ins_handled`, `long_silences`, `long_silences_per_turn` from `naturalness.py`.
- `session_errors` (F-14). `full` is true only when every persona ran `FULL_REPS` times.

#### `src/voice_arch/naturalness.py`
Pure functions on the session report's chat items. `long_silences(items)`: agent-owed gaps (user stopped speaking →
agent started speaking, using the report's timestamps) strictly > 2.0 s (U-11). `barge_ins(items)`: agent messages flagged
interrupted that follow a user utterance; handled when the next agent message is not a near-duplicate of the interrupted
one (normalised text, ratio ≥ 0.9 = duplicate, `difflib.SequenceMatcher`) (U-12). `latency_rows(items)` → list of
`e2e_latency` floats or None per agent turn. Field names: read them from the installed `ChatMessage.metrics`
(`e2e_latency`, `interrupted`, timestamps) and document the mapping in the module docstring.

#### `src/voice_arch/rate.py` (CLI `python -m voice_arch.rate --arch a|b|c --rating 1-5 [--notes "…"]`)
Logs one `tracked_run(sub="human", run_name=f"human-{arch}")` with metric `human_rating` and tag `source=human`; validates
1 ≤ rating ≤ 5. Never logs `exact_rate` (U-6).

## Docs
- `README.md` runbook: OpenRouter dedicated key with a 50 $ limit; `docker compose up -d livekit`; `.env`; start the worker
  (`python -m voice_arch.worker start`); a smoke sweep (`--personas self_correction --reps 1`); full sweeps for a, b, c, one
  at a time (one sweep per key at a time, F-12); the browser call + `rate.py`; expected duration (~30 calls ≈ 1–1.5 h).
- `PROJECT.md` `## Enseignements` after the sweeps: the table per arch (exact_rate, latency p50/p90, cost, naturalness,
  human rating) and the decision under task success > latency > cost (U-14); `## Suite`: #21, #22, #25 as relevant.

## Tests

#### `tests/test_personas.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_5_persona_expected_problem_type_is_valid_enum` | shipped personas load; `vague_problem` expects `plumbing` | U-5 |
| `test_u_7_persona_expected_slot_exists_in_calendar` | a persona with `ST_20990101_0900` → `PersonaError` naming it | U-7 |
| `test_personas_cover_the_six_behaviours` | ids/behaviours = the 6 listed | goal |

#### `tests/test_scoring.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_f_5_timeouts_and_errors_count_as_misses_in_exact_rate` | 8 scored exact + 1 timeout + 1 agent_lost → `exact_rate == 0.8` | F-5 |
| `test_u_3_agent_timeout_counts_as_not_exact_in_denominator` | 1 exact + 1 timeout → 0.5 | U-3 |
| `test_f_6_caller_fault_excluded_and_counted` | 2 exact + 1 caller_fault → `exact_rate == 1.0`, `n_caller_fault == 1` | F-6 |
| `test_u_1_sweep_with_fewer_reps_than_full_logs_smoke_metrics_only` | `full=False` → keys all start with `smoke_`, no `exact_rate` | U-1 |
| `test_f_7_latency_aggregation_tolerates_missing_and_all_missing_e2e` | turns [1.0, None, 3.0] → p50 2.0, missing 1; all None → no `latency_p50_s` key | F-7, U-10 |
| `test_u_10_no_turns_omits_latency_metrics` | zero turns → no latency keys, `latency_turns == 0` | U-10 |
| `test_u_13_missing_field_counts_as_incorrect` | timeout row (no record) → every `field_*_acc` counts it wrong | U-13 |

#### `tests/test_naturalness.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_11_exactly_two_seconds_is_not_long` | agent gap 2.0 s → 0; 2.01 s → 1 | U-11 |
| `test_u_11_caller_side_gap_is_not_a_long_silence` | agent stops, caller answers after 3 s → 0 | U-11 |
| `test_u_12_verbatim_repeat_after_interrupt_is_not_handled` | interrupted "Your number is 415…" then same text → barge_ins 1, handled 0 | U-12 |
| `test_u_12_new_reply_after_interrupt_is_handled` | interrupted then a different answer → handled 1 | U-12 |

#### `tests/test_runner.py` (fakes for the room / dispatch / caller seams; no network)
| Test | Given → expected | Source |
|---|---|---|
| `test_f_1_runner_times_out_a_call_whose_caller_never_hangs_up` | fake result never arrives, `call_timeout_s=0.1` → row `outcome=timeout`, room deleted | F-1 |
| `test_f_2_sweep_aborts_when_no_agent_joins_within_deadline` | no agent participant → run FAILED after the first call, no 2nd room created | F-2 |
| `test_f_3_missing_result_scores_as_failure` | agent leaves without a result → `outcome=agent_lost` | F-3 |
| `test_f_4_402_aborts_sweep_and_creates_no_further_rooms` | first result `error` contains HTTP 402 → run FAILED, 1 room created | F-4 |
| `test_f_6_caller_error_close_is_classified_caller_fault` | fake caller session raises → `outcome=caller_fault`; 2/10 → run FAILED | F-6 |
| `test_f_8_caller_does_not_speak_before_first_agent_turn` | `CallerAgent` has no `on_enter` reply; instructions contain the wait rule | F-8 |
| `test_f_14_session_errors_are_counted` | report with 2 errors → `session_errors == 2` | F-14 |
| `test_f_12_cost_absent_when_key_read_fails` | SpendTracker read fails after → metrics without `cost_usd`, run FINISHED | F-12 |

#### `tests/test_rate.py`
| Test | Given → expected | Source |
|---|---|---|
| `test_u_6_rating_run_never_logs_exact_rate` | `rate --arch b --rating 4` on sqlite MLflow → metric `human_rating=4`, no `exact_rate` | U-6 |
| `test_rating_out_of_range_refused` | rating 0 / 6 → error before any MLflow call | input |

#### `tests/integration/test_one_call.py` (`@pytest.mark.integration`, live stack + OpenRouter)
| Test | Given → expected | Source |
|---|---|---|
| `test_one_live_call_produces_a_scored_row` | worker running, persona `self_correction`, arch `a`, 1 rep → one row with `outcome` in {scored, timeout}, a `CallResult` received | goal |

**Done when:** unit tests + hooks pass, the live call test passes, three full sweeps (a, b, c) are FINISHED in MLflow
`voice-arch/conversations`, at least one human rating per arch is logged, the app card shows `exact_rate`, and PROJECT.md
Enseignements states the decision.
