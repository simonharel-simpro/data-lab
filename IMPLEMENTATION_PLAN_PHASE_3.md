# Phase 3 — Simulated caller, sweep runner, scoring, decision, human ratings

**Depends on Phase 2 (already exists):** `booking/record.py` (`BookingRecord`, `ExpectedRecord` extra="forbid",
`SCORED_FIELDS`, `is_exact(actual|None, expected) -> (bool, per_field)`), `booking/calendar.py` (`CALENDAR`, 12 slots;
free ones: `ST_20261109_1400`, `ST_20261110_0900`, `ST_20261110_1400`, `ST_20261111_1100`, `ST_20261111_1600`,
`ST_20261112_1400`, `ST_20261113_0900`, `ST_20261113_1100`, `ST_20261113_1600`), `ProblemType`, `agents/registry.py`
(`Arch`), `result.py` (`CallResult`: room, arch, run_id, record, report = `SessionReport.to_dict()`, close_reason,
error, http_status, session_errors; `RESULT_TOPIC = "voice-arch.result"`), the worker `agent_name="booking-agent"`
(dispatch metadata `{"arch": "a|b|c", "run_id": …}`; it greets first, ends the session after confirmation, then sends
one `CallResult` on the text stream and leaves). **Phase 1:** `VoiceSettings` (incl. `caller_llm_model`,
`caller_temperature`, `call_timeout_s`, `agent_join_timeout_s`), `make_stt/make_tts/make_llm`, `SpendTracker` /
`key_usage` (`limit_remaining`), `dispatch.py`, `token.py` (`make_token`), datalab `load`, `Settings`, `preflight`,
`tracked_run`. **Agent:** `python-fastapi`.

Context: a sweep = one arch × 6 personas × reps, one MLflow run (D-9). The caller is an `AgentSession` hosted in the
runner on a self-connected `rtc.Room` inside `livekit.agents.testing.fake_job_context(room=room)` (no worker). Decision
rule D-15; cost includes the caller (D-16). LiveKit names: `rtc.Room().connect(url, token)`,
`room.register_text_stream_handler(topic, handler)`, participant `kind` (agents = `ParticipantKind.PARTICIPANT_KIND_AGENT`),
agent state attribute `"lk.agent.state"` (= `livekit.agents.types.ATTRIBUTE_AGENT_STATE`), `session.say(text,
allow_interruptions=False)`, `LiveKitAPI(url=http(s) form, api_key, api_secret).room.delete_room(DeleteRoomRequest(room=…))`.

## Data

#### `data/personas.jsonl` (6 lines)
`{"id", "behaviour", "instructions", "interjections": [str], "expected_record": {5 scored fields}}`, US formats, each
`slot_id` a FREE slot above. `self_correction` (corrects the phone's last digit) · `out_of_order` (problem and address
before name) · `interrupter` (`interjections`: ["Sorry — can you repeat the time?", "Wait, one thing —"]) ·
`slot_change` (during the agent's read-back says "actually, Thursday at 2 instead" → expected `ST_20261112_1400`, U-18)
· `speller` (Siobhan Smyth, spells the surname) · `vague_problem` ("the water's acting weird" → `plumbing`). Instructions:
answer naturally, never invent fields, wait for the agent to speak first (F-8), say goodbye when the agent does.

## Source

#### `src/voice_arch/personas.py`
`Persona(BaseModel)`: `id`, `behaviour`, `instructions`, `interjections: list[str] = []`, `expected_record:
ExpectedRecord`. `load_personas(path) -> list[Persona]`: ids unique; exactly the 6 behaviours above; `slot_id` exists
AND is not booked (U-7, U-17); problem_type valid (U-5) — errors → `PersonaError(line, reason)`.

#### `src/voice_arch/caller.py`
`CallerAgent(Agent)`: instructions = persona instructions + "Never speak first." (no `on_enter` reply, F-8).
`make_caller_session(settings) -> AgentSession` (STT/TTS from settings; LLM `make_llm(settings,
model=settings.caller_llm_model, temperature=settings.caller_temperature)`, U-20). The caller never ends the call: the
call ends when the agent's result arrives or a deadline hits (runner).

#### `src/voice_arch/call_env.py`
`CallEnv(Protocol)` — the seam the runner tests fake: `async create_dispatch(room, arch, run_id)`, `async
connect_caller(room) -> CallerHandle`, `async delete_room(room)`. `CallerHandle(Protocol)`: `async wait_agent(timeout)
-> bool`, `async wait_result(timeout) -> CallResult | None` (None on timeout), `agent_left: bool`, `caller_error: str |
None`, `async interject(text)`, `agent_speaking_for() -> float`, `async close()`. `LiveKitCallEnv(settings)`: real
implementation (token via `make_token`, `rtc.Room`, the text-stream handler parsing `CallResult.from_json`, the caller
session started inside `fake_job_context(room=room)`, `participant_disconnected` → `agent_left`, caller `error`/`close`
events → `caller_error`).

#### `src/voice_arch/call.py`
`CallRow(BaseModel)`: persona, rep, room, outcome (`Outcome(StrEnum)`: scored, timeout, agent_lost, caller_fault,
provider_error), record, exact, per_field, latencies (`list[float | None]`), barge_ins, barge_ins_handled,
long_silences, agent_turns, session_errors, http_status, error.
`async run_one_call(env, persona, arch, run_id, rep, *, call_timeout_s, join_timeout_s) -> CallRow`:
room `va-{run_id[:8]}-{arch}-{persona.id}-{rep}-{uuid4().hex[:6]}`; dispatch; connect; `wait_agent` false →
`raise AgentNeverJoined` (F-2); while waiting for the result, if `persona.interjections` remain and
`agent_speaking_for() ≥ 1.0`, `interject(next)` (barge-in, U-12); result → `CallResult.http_status` in (401, 402) →
`raise ProviderAuthStop` (F-4, before any other classification); `caller_error` → `caller_fault` (F-6); `agent_left`
without result → `agent_lost` (F-3); no result by `call_timeout_s` → `timeout` (F-1); else `scored` with
`is_exact(result.record, persona.expected_record)` and the report-derived counters (`naturalness.py`). Always
`delete_room` and `close()` in `finally`.

#### `src/voice_arch/runner.py` (CLI `python -m voice_arch.runner --arch a|b|c [--personas id,…] [--reps N]`)
`async run_sweep(env, personas, arch, reps, settings, *, project, dl_settings) -> str` (run id):
1. Before any LiveKit I/O: settings, `load()`, `preflight()`, `load_personas()`; budget check (U-21): `key_usage().
   limit_remaining` < 1.2 × the last FINISHED full sweep's `cost_usd` (MLflow search in `voice-arch/conversations`) →
   refuse with a message; no previous sweep → warning only.
2. `with tracked_run(project, dl_settings, run_name=f"arch-{arch}", sub="conversations") as run_id, SpendTracker(key)
   as spend:` loop persona × rep, append each `CallRow` to `results/<run_id>.jsonl` at once; `AgentNeverJoined` /
   `ProviderAuthStop` propagate → run FAILED (F-2, F-4).
3. Log params (arch, stt/tts/llm/voice, caller model + temperature, providers, reps, personas, FULL_REPS, timeouts,
   summarize flag from the first result), metrics `scoring.aggregate(rows, full=…)` + `cost_usd` and
   `cost_per_call_usd` (if known), artifact `per_conversation.json`. `full` = all 6 personas × `FULL_REPS`.
4. `caller_fault` > 10 % of rows → raise after logging (F-6).

#### `src/voice_arch/naturalness.py` (pure; input = `SessionReport.to_dict()`)
Reads `report["chat_history"]["items"]` (dicts with `type == "message"`, `role`, `interrupted`, `content`,
`metrics.started_speaking_at`, `metrics.stopped_speaking_at`, `metrics.e2e_latency`) and `report["events"]` (`type ==
"error"` → session errors, F-14); verify these keys against an actual `to_dict()` output from the integration run and
document the mapping. `latencies(report) -> list[float | None]` (one per assistant turn) · `long_silences(report) ->
int`: assistant turns whose start − previous user stop > 2.0 s strictly (U-11; caller think-time is not measured) ·
`barge_ins(report) -> tuple[int, int]`: interrupted assistant messages, handled when the next assistant message's text
similarity (`difflib.SequenceMatcher` on normalised text) < 0.9 (U-12).

#### `src/voice_arch/scoring.py` (pure)
`FULL_REPS: Final = 5`. `aggregate(rows, *, full: bool) -> dict[str, float]` (every key prefixed `smoke_` unless full,
U-1): denominator `n = scored + timeout + agent_lost` (`caller_fault` excluded, F-6, U-3); `exact_rate = exact/n`;
`field_<f>_acc` (missing = wrong, U-13); `n_<outcome>` for each outcome; latency over the pooled non-None turns:
none → no keys; one → p50 = p90 = it; ≥ 2 → `statistics.quantiles(n=10, method="inclusive")` [4] and [8] (U-10);
`latency_turns`, `latency_turns_missing`; `barge_ins`, `barge_ins_handled`, `long_silences`, `long_silences_per_turn`,
`session_errors`. `cost_per_call(cost_usd, rows) -> float | None` = cost / n (U-19).

#### `src/voice_arch/decide.py` (pure + CLI `python -m voice_arch.decide`)
`ArchSummary(arch, exact_rate, n, latency_p50_s | None, cost_per_call_usd | None, human_rating_mean | None)`.
`pick_arch(summaries) -> Decision(winner, ranking, production_ready: bool, reason)` (D-15, U-16): best exact_rate; archs
within 2 calls of it (`(best − r) × n ≤ 2`) tie → lowest latency p50 (None last) → lowest cost (None last); production
ready iff winner `exact_rate ≥ 0.9` and latency p50 < 1.2. `human_rating_mean(ratings) -> float | None` = mean (U-23),
reported, never ranks. The CLI reads the latest FINISHED full run per arch + human runs, prints the table and decision
for PROJECT.md.

#### `src/voice_arch/rate.py` (CLI `--arch a|b|c --rating 1-5 [--notes …]`)
Validates 1 ≤ rating ≤ 5 before MLflow; `tracked_run(sub="human", run_name=f"human-{arch}")`, metric `human_rating`, tag
`source=human`, notes as a tag. Never logs `exact_rate` (U-6).

## Docs
`README.md` runbook: dedicated OpenRouter key with a 50 $ limit; `docker compose --profile voice up -d livekit`;
`.env`; `python -m voice_arch.worker start`; smoke (`--personas self_correction --reps 1`); full sweeps a, b, c one at a
time (one sweep per key at a time); browser call + `rate.py`; `decide`; ~30 calls ≈ 1–1.5 h per sweep.
`PROJECT.md` `## Enseignements`: the decide table + decision + note that cost includes the simulated caller; `## Suite`.

## Tests (fake `CallEnv` / `CallerHandle` with scripted results; MLflow on tmp sqlite; no network)

| File · test | Given → expected | Source |
|---|---|---|
| test_personas · `test_u_5_persona_expected_problem_type_is_valid_enum` | shipped personas load; `vague_problem` expects `plumbing` | U-5 |
| test_personas · `test_u_7_persona_expected_slot_exists_in_calendar` | slot `ST_20990101_0900` → `PersonaError` naming it | U-7 |
| test_personas · `test_u_17_persona_expected_slot_is_free` | slot `ST_20261109_0900` (booked) → `PersonaError` | U-17 |
| test_personas · `test_u_25_extra_expected_key_rejected` | `expected_record` with `zip` → `PersonaError` | U-25 |
| test_call · `test_f_1_timeout_when_no_result_arrives` | result never arrives, timeout 0.1 → `outcome=timeout`, room deleted | F-1 |
| test_call · `test_f_2_agent_never_joins_raises` | `wait_agent` False → `AgentNeverJoined` | F-2 |
| test_call · `test_f_3_agent_left_without_result_is_agent_lost` | `agent_left` True, no result → `agent_lost` | F-3 |
| test_call · `test_f_4_402_raises_before_caller_fault` | result `http_status=402` and `caller_error` set → `ProviderAuthStop` | F-4 |
| test_call · `test_f_6_caller_error_is_caller_fault` | `caller_error="tts 500"`, result arrives → `caller_fault` | F-6 |
| test_call · `test_interrupter_fires_interjections_while_agent_speaks` | speaking 1.2 s, 2 interjections → `interject` called twice, never more | U-12 |
| test_call · `test_f_8_caller_agent_does_not_speak_first` | `CallerAgent` has no `on_enter`; instructions contain "Never speak first." | F-8 |
| test_runner · `test_f_2_sweep_aborts_after_first_call_when_no_agent` | env whose agent never joins → run FAILED, 1 room created | F-2 |
| test_runner · `test_f_4_402_aborts_sweep_and_creates_no_further_rooms` | first result 402 → run FAILED, 1 room | F-4 |
| test_runner · `test_f_6_more_than_10_percent_caller_faults_fails_the_run` | 2/10 caller_fault → FAILED, rows still in JSONL | F-6 |
| test_runner · `test_u_21_sweep_refuses_to_start_when_remaining_credit_below_estimate` | remaining 5.0, last full sweep cost 10.0 → refused, no room | U-21 |
| test_runner · `test_u_1_partial_sweep_logs_smoke_metrics_only` | 1 persona × 1 rep → metrics all `smoke_*` | U-1 |
| test_runner · `test_f_12_cost_absent_when_key_read_fails` | 2nd key read fails → no `cost_usd`, run FINISHED | F-12 |
| test_runner · `test_u_20_caller_llm_uses_configured_model_and_temperature` | params `caller_llm_model`, `caller_temperature` = settings | U-20 |
| test_scoring · `test_f_5_timeouts_and_errors_count_as_misses_in_exact_rate` | 8 exact + 1 timeout + 1 agent_lost → 0.8 | F-5 |
| test_scoring · `test_u_3_agent_timeout_counts_as_not_exact_in_denominator` | 1 exact + 1 timeout → 0.5 | U-3 |
| test_scoring · `test_f_6_caller_fault_excluded_and_counted` | 2 exact + 1 caller_fault → 1.0, `n_caller_fault == 1` | F-6 |
| test_scoring · `test_f_7_latency_tolerates_missing` | turns [1.0, None, 3.0] → p50 2.0, `latency_turns_missing == 1` | F-7 |
| test_scoring · `test_single_latency_turn_is_p50_and_p90` | [1.4] → p50 1.4, p90 1.4 | U-10 |
| test_scoring · `test_u_10_no_turns_omits_latency_metrics` | none → no latency keys, `latency_turns == 0` | U-10 |
| test_scoring · `test_u_13_missing_field_counts_as_incorrect` | 1 exact + 1 timeout → every `field_*_acc == 0.5` | U-13 |
| test_scoring · `test_u_19_cost_per_call_uses_exact_rate_denominator` | cost 3.0, 8 scored + 1 timeout + 1 caller_fault → 3.0/9 | U-19 |
| test_naturalness · `test_u_11_exactly_two_seconds_is_not_long` | gap 2.0 → 0; 2.01 → 1 | U-11 |
| test_naturalness · `test_u_12_verbatim_repeat_after_interrupt_is_not_handled` | interrupted "Your number is 415…" then same text → (1, 0) | U-12 |
| test_naturalness · `test_u_12_new_reply_after_interrupt_is_handled` | interrupted then a different answer → (1, 1) | U-12 |
| test_naturalness · `test_f_14_session_errors_are_counted` | report with 2 error events → 2 | F-14 |
| test_decide · `test_u_16_arch_within_exact_margin_falls_back_to_latency` | A 27/30 2.3 s, B 26/30 2.0 s → B (1 call apart) | U-16 |
| test_decide · `test_pick_arch_outside_margin_prefers_exact` | A 28/30 2.5 s, B 25/30 1.9 s → A | U-16 |
| test_decide · `test_u_16_no_arch_meets_bar_still_ranks_and_flags` | best 0.8 → winner set, `production_ready False` | U-16 |
| test_decide · `test_u_23_human_ratings_aggregate_by_mean_per_arch` | [4, 5, 3] → 4.0; [] → None | U-23 |
| test_rate · `test_u_6_rating_run_never_logs_exact_rate` | rating 4 → `human_rating == 4`, no `exact_rate` | U-6 |
| test_rate · `test_rating_out_of_range_refused` | 0 / 6 → error before any MLflow call | input |
| integration/test_one_call · `test_one_live_call_produces_a_row` | worker running, `self_correction`, arch a → one `CallRow`, outcome in {scored, timeout}; report keys used by naturalness present | goal |

**Done when:** unit tests + hooks pass, the live call passes, full sweeps a, b, c FINISHED in `voice-arch/conversations`,
≥ 1 human rating per arch, `decide` output in PROJECT.md, the app card shows `exact_rate`.
