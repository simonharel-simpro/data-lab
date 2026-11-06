# Implementation notes (deviations from the plan)

## Phase 1 part A

- Plan assumed: the only new runtime deps are the livekit packages and httpx.
  Territory was: the declared-deps hook requires every directly imported package to be declared; `settings.py` imports pydantic-settings and `budget.py` imports mlflow (both only transitive via datalab).
  I did: declared `mlflow==3.17.2` and `pydantic-settings~=2.16` (the exact pins datalab already locks, as mini-rag does), no new package in the lock.
  One-off or pattern?: likely recurs — candidate for the scaffold template's dependency checklist.
- Plan assumed: `from livekit.agents import RawFunctionTool`-style import (name only in the prose).
  Territory was: `RawFunctionTool` lives in `livekit.agents.llm` in 1.8.8.
  I did: import it from `livekit.agents.llm`.
  One-off or pattern?: one-off.
- Plan assumed: `args_correct` compares per-arg values; silent on the key sets.
  Territory was: an LLM can emit an extra or omit an expected arg.
  I did: strict key-set equality (extra or missing key -> False), so a malformed call never counts as correct. Affects only the stage-1 LLM ranking; flagged in the report.
  One-off or pattern?: one-off.
- Plan assumed: `normalize_name` joins spelled letters, then drops `.` and `'`.
  Territory was: "S. M. Y. T. H." only joins if the dots are gone first.
  I did: drop `.` and `'` first, then join the single-letter runs.
  One-off or pattern?: one-off.
- Plan assumed: LiveKit healthcheck only if the image ships a usable binary.
  Territory was: the image ships busybox (`wget` applet); LiveKit was not started here (instruction), so the check is declared but not exercised live.
  I did: `wget -q --spider http://127.0.0.1:7880`; verify at the first `docker compose --profile voice up -d` (Phase 1 part B).
  One-off or pattern?: one-off.
- Plan assumed: pytest config only `asyncio_mode = "auto"`.
  Territory was: pytest-asyncio 1.4.0 warns when `asyncio_default_fixture_loop_scope` is unset.
  I did: set it to `function`.
  One-off or pattern?: one-off.

## Phase 1 part B

- Plan assumed: `field_errors` (part A) finds a name in a transcript as written.
  Territory was: it kept punctuation, so "Maria Garcia, that's ..." never matched "Maria Garcia"; every real STT transcript carries commas, so the bench would have scored noise (found by `load_utterances` on the first shipped corpus).
  I did: normalise both sides with `normalize_text` after the field normaliser (new test `test_field_errors_name_followed_by_punctuation_still_matches`).
  One-off or pattern?: likely recurs — scoring helpers need a test on punctuated real-looking transcripts.
- Plan assumed: TTS "intelligible = `field_errors` of the round-trip transcript all False", but the agent lines carry no field truth.
  Territory was: no truth values for `data/agent_lines.txt`.
  I did: `field_errors(transcript, {"line": line})` (unknown field = `normalize_text` containment of the whole line); lines are digit-free; the judge hears the first rep of each line only.
  One-off or pattern?: one-off.
- Plan assumed: `build_corpus` sync-looking, manifest lists ids, model, voice, wav hashes.
  Territory was: `tts.synthesize` is async; an edited utterance text with the same id would reuse stale audio.
  I did: `build_corpus` is `async`, the manifest also stores each text's sha256. Bench seams take small Protocols (`seams.py`) instead of the concrete LiveKit classes so fakes need no cast; the corpus is built inside the run so its cost is attributed.
  One-off or pattern?: one-off.
- Plan assumed: stage-1 candidate set picks winners that satisfy D-17.
  Territory was: the LLM winner (`google/gemini-3.5-flash-lite`) is the simulated caller's fixed model (D-17 says distinct); and `nova-3` writes address numbers as words, which `normalize_address` does not map.
  I did: kept the plan's rules (defaults = winners) and escalated both in the report; no scoring change after seeing results.
  One-off or pattern?: likely recurs — number words in spoken addresses will also hit Phase 2's exactness scoring.
- Plan assumed: spike may need `openrouter_adapters.py`.
  Territory was: the LiveKit openai plugins work against OpenRouter for STT (assemblyai, deepgram, openai), TTS (gemini corpus voice `Kore`, deepgram, elevenlabs) and LLM.
  I did: no adapter. `CORPUS_VOICE = "Kore"` for the Gemini corpus TTS (the plan named the model but no voice).
  One-off or pattern?: one-off.
- Plan assumed: existing tests assert the placeholder defaults.
  Territory was: `test_settings`/`test_audio` assert the pre-bench defaults; the plan requires defaults = winners.
  I did: updated those expected values to the winners (spec-mandated; not a loosening). Needs a `Test-Change:` trailer at commit.
  One-off or pattern?: one-off.
- Plan assumed: the stage-1 bench lives in `bench.py` (plus `corpus.py`, `winners.py`).
  Territory was: constants and the three measurement loops pushed `bench.py` past the 200-line module limit.
  I did: two unplanned splits — `candidates.py` (the bench candidate constants, keeps `bench.py` < 200 lines) and `bench_runs.py` (`run_stt` / `run_tts` / `run_llm` measurements).
  One-off or pattern?: one-off.
- Third unplanned split: `bench_record.py` (`select`, `slug`, `appender`, `record_outcome`, `Outcome`, `Row`/`Emit`) keeps `bench.py` under 200 lines; the unused `Outcome.rows` field was dropped. Tests import `select` from `bench_record`.

## Phase 1 — part C

- Plan assumed: stage-1 winners can all be the defaults (D-17: caller LLM fixed and distinct from the agent's).
  Territory was: the agent default `google/gemini-3.5-flash-lite` collided with `caller_llm_model`.
  I did: provisional `caller_llm_model = "anthropic/claude-haiku-5.5"` (20/20 in the LLM bench), temperature 0.7, plus a settings validator refusing caller == agent (ESC-1-2, user confirms later).
  One-off or pattern?: one-off.

## Phase 2

- Plan assumed: `parse_metadata`, `build_result` and the pinned `TURN_HANDLING` / `MAX_TOOL_STEPS` live in `worker.py`, unit-tested without LiveKit.
  Territory was: the plan also builds `AgentServer(ws_url=settings...)` at module level (job processes pickle `entry` by module reference), so importing `worker.py` needs a full `VoiceSettings` (keys from the env or `.env`).
  I did: put those pure parts (+ `SessionWatch`, `error_result`) in `worker_logic.py`; `worker.py` keeps the server, `entry`, `send_result`, `run_call`. Two extra tests import `worker.py` under the `voice_settings` fixture.
  One-off or pattern?: likely recurs — any LiveKit worker module that reads settings at import.
- Plan assumed: the worker passes `providers=s.provider_list` to `make_llm`.
  Territory was: with the default pin (deepinfra, gmicloud, parasail, fp8, no fallback) OpenRouter answers 404 "No endpoints found" for the agent default `google/gemini-3.5-flash-lite`; the stage-1 LLM bench ran with `llm_providers: none` and passed.
  I did: provisional `make_llm(settings)` without a pin in the worker and the live tests (ESC-2-1). Superseded: pinned to Google's providers (`google-vertex,google-ai-studio`, no fallback, `openrouter_quantization` now optional and unset), user decision option C.
  One-off or pattern?: likely recurs — the provider pin and the model choice must be decided together.
- Plan assumed: a task's `on_enter` is `await self.session.generate_reply()`.
  Territory was: (1) after the previous step's assistant message the request ends with a model turn and Gemini via OpenRouter answers 400 "Requests ending with a model turn are not supported" (the TaskGroup hand-off then dies); (2) awaiting the handle inside `on_enter` buys nothing (the built-in tasks do not).
  I did: `generate_reply(chat_ctx=ends_with_user_turn(self.chat_ctx))` (an ephemeral copy gets a stand-in user turn, `CALLER_WAITING`; the agent's own context is untouched), not awaited. The greeting of `BookingFlowAgent` is still awaited before the group starts.
  One-off or pattern?: likely recurs — every Gemini-backed LiveKit task or handoff that replies without a user turn.
- Plan assumed: C's `update_record(field, value)` is `apply_record`.
  Territory was: `apply_record` has no availability check, so `update_record("slot_id", "ST_20261109_0900")` would write a booked or unknown slot into the record.
  I did: `slot_id` goes through `apply_choose_slot` (same rules as `choose_slot`, releases the old slot); other fields use `apply_record`; unknown fields return error text. Still never completes a task.
  One-off or pattern?: one-off.
- Plan assumed: the caller can talk once the agent has greeted.
  Territory was: under B and C the greeting precedes the hand-off into the first task; a caller turn sent in that window lands in the previous agent's context and the name task asks for the name again.
  I did: the live tests wait until `session.current_agent` is a `StepTask` before the first turn. Phase 3's caller must wait for the first question, not only the greeting (F-8).
  One-off or pattern?: likely recurs — Phase 3 runner.
- Plan left open: malformed `run_id` and `part` values.
  I did: `parse_metadata` raises `UnknownArchError` for a non-string `run_id` (absent or empty stays "manual"); `check_slots` answers "Use morning or afternoon." for any other `part`. Low stakes, one-off.

## Phase 3

- Plan assumed: `CallEnv.connect_caller(room)` and `LiveKitCallEnv` inside `call_env.py`.
  Territory was: the caller needs the persona's instructions and, for B and C, a different start (below); and `call_env.py` must stay LiveKit-free so `call.py`, `scoring.py` and `decide.py` are too.
  I did: `connect_caller(room, persona, arch)`; protocols stay in `call_env.py`, the real env is `livekit_env.py` (+ `live_caller.py` for the handle, 200-line limit). An import-linter contract keeps the pure modules LiveKit-free.
  One-off or pattern?: one-off.
- Plan assumed: the caller can answer once the agent has greeted (Phase 2 note: it must wait for the first question under B and C).
  Territory was: `AgentSession.start` on the caller blocks until the agent participant links, and there is no event for "the first question". A's greeting is not a question (the agent then waits), B/C hand off to the first task right after the greeting.
  I did: `session.start` runs in a background task (so `wait_agent` can time out, F-2); the handle tracks `lk.agent.state` and counts the agent's speaking turns; B/C keep the caller's audio input off until the greeting has ended (`listen_after = 1`), A listens at once. A heuristic: the caller of A answers the greeting, the caller of B/C answers the first question.
  One-off or pattern?: likely recurs — any simulated caller against a greet-then-hand-off agent.
- Plan assumed: dispatch metadata `{"arch", "run_id"}` is already sent.
  Territory was: `dispatch.dispatch()` only sent `{"arch"}`; the worker would have logged every sweep call as run "manual".
  I did: `dispatch(settings, arch, room, run_id=None)` with a pure `metadata_json` (round-trip tested against `parse_metadata`).
  One-off or pattern?: one-off.
- Plan left open: how `decide` gets the integer exact count and the arch of a run; how a human run is tied to an arch.
  I did: `aggregate` also emits `n_exact`; sweep runs carry tags `arch` and `full`; human runs carry tag `arch` (run name stays `human-<arch>`). `decide` sums `n_scored + n_timeout + n_agent_lost` for `n`.
  One-off or pattern?: one-off.
- Plan left open: `session_errors` source for a row (worker count in `CallResult.session_errors` vs error events in the report).
  I did: the report's error events when the report exists (plan: report-derived counters), the worker's count otherwise. `CallRow` also keeps `summarize_chat_ctx` and `max_tool_steps` so the run params come "from the first result".
  One-off or pattern?: one-off.
- Plan assumed: the report keys `naturalness` reads can be verified on the live call.
  Territory was: both live calls timed out (see ESC-3-2), so no audio report was seen. Checked on a text-mode `make_session_report(...).to_dict()` instead: `chat_history.items[*]` has `type`, `role`, `interrupted`, `content`, `metrics.started_speaking_at`, `metrics.stopped_speaking_at`; `events[*].type` has `error`. `metrics.e2e_latency` is absent in text mode (no STT/TTS), so its presence in an audio call is still unverified.
  I did: coded against the documented `MetricsReport`; a missing key is None (F-7). The first successful audio call must confirm `e2e_latency`.
  One-off or pattern?: one-off.
- Plan left open: when the budget is checked between calls.
  I did: after every call except the last, so a finished sweep is never failed for money already spent (its `cost_usd` still counts next time).
  One-off or pattern?: one-off.
- Plan assumed: the run params list "providers".
  Territory was: neither the worker (ESC-2-1) nor the caller pinned an OpenRouter provider.
  I did: param `llm_providers = none` (as the stage-1 bench). Superseded: `llm_providers` is now the agent pin list and `caller_llm_providers = none`.
  One-off or pattern?: one-off.

## Voice-arch fix branch (pin + stall)

- Plan assumed: the stall was a hung LLM stream or a preemptive-generation race (brief suspects).
  Territory was: neither. The LLM answers in about 1 s with an empty completion (0 tokens); the pin (Task 1) and disabling preemptive generation (tried first, the call still stalled) both did not fix it.
  I did: `retry_on_empty_completion` in new `llm_guard.py`, enabled by `make_llm(..., retry_empty=True)` for the worker agent only. The caller LLM and the bench keep the plain LLM (an empty reply in the bench must stay visible; the caller factory protocol has no such argument): a caller-side empty completion would still stall a sweep call. Preemptive generation stays disabled (no evidence it helps; small cost to latency); revisit if latency matters.
  One-off or pattern?: likely recurs: any LiveKit agent on Gemini via OpenRouter.
- Plan assumed: `test_f_16_turn_handling_and_tool_steps_are_pinned` asserts the old `TURN_HANDLING` value.
  Territory was: the brief asks to disable preemptive generation explicitly, which changes that value.
  I did: updated that test's expected dict (`"preemptive_generation": {"enabled": False}`); a planned test edit made on the orchestrator's instruction (Test-Change trailer needed in the commit: ESC-3-2).
  One-off or pattern?: one-off.
- Plan assumed: a live call finishes within `call_timeout_s` = 240 s.
  Territory was: a call with the `self_correction` persona needs more than 240 s (real-time TTS read-backs of 12 to 15 s, the caller arguing with a correct read-back).
  I did: ran the live checks with `VOICE_ARCH_CALL_TIMEOUT_S` raised (env only, default unchanged) and used `worker dev`, because the `start` worker marks itself unavailable above 0.7 CPU load and the host was busy.
  One-off or pattern?: likely recurs: the sweep's 240 s default may make many self_correction calls `timeout`; decide before the sweeps.

## Escalations
- ESCALATION(ESC-1-1) [resolved] phase=1 tier=reversible :: STT winner depends on address number scoring: nova-3 writes street numbers as words (15 of its 19 errors); normalize_address maps no number words. Option A keep plan scoring (assemblyai wins) / B add number-word mapping and re-run (nova-3 likely wins on latency). => Kept the plan's U-4 scoring (option A): normalize_address is specified without number words, and changing scoring after seeing results would bias the bench. assemblyai/universal-3-6-pro stays the STT winner. Revisit if Phase 2 exact-booking fails on number-word addresses.
- ESCALATION(ESC-1-2) [resolved] phase=1 tier=reversible :: LLM bench winner google/gemini-3.5-flash-lite equals the caller model default, but D-17 requires caller != agent. Provisional: agent = gemini-3.5-flash-lite (bench winner), caller = anthropic/claude-haiku-5.5 (also 20/20) at temperature 0.7. User to confirm which model plays the caller. => User 2026-11-06: caller = anthropic/claude-haiku-5.5 @ temperature 0.7 (agent = google/gemini-3.5-flash-lite).
- ESCALATION(ESC-2-1) [resolved] phase=2 tier=reversible :: The plan pins OpenRouter providers (deepinfra, gmicloud, parasail, fp8, no fallback) for the worker LLM, but no such endpoint serves `google/gemini-3.5-flash-lite` (404). Provisional: the worker and live tests run unpinned, like the stage-1 bench. Options: A keep unpinned (agent runs are then not routing-reproducible) / B pick a model that a pinned upstream serves and re-bench / C pin to Google's providers. User decides before Phase 3 sweeps. => User 2026-11-06: option C — pin the worker LLM to Google's own OpenRouter providers for google/gemini-3.5-flash-lite.
- ESCALATION(ESC-2-2) [resolved] phase=2 tier=reversible :: OpenRouter provider pin (deepinfra,gmicloud,parasail fp8, no fallback) serves no google/gemini-3.5-flash-lite endpoint (404). Provisional A: worker LLM unpinned like the stage-1 bench (routing not reproducible). B: pick a pinned-served agent model and re-bench. C: pin to Google providers. User decides before Phase 3 sweeps. => Duplicate of ESC-2-1 (recorded twice: subagent + orchestrator); tracked there.
- ESCALATION(ESC-3-1) [resolved] phase=3 tier=reversible :: `Outcome.PROVIDER_ERROR` is in the plan's enum but no rule assigns it, and it is outside the `exact_rate` denominator (scored + timeout + agent_lost). Provisional: never emitted; a result that carries `error` / a non-auth `http_status` is `scored` by its record (an unfinished record is simply not exact). Option A keep (provider failures count against the arch) / B emit it for a result with a non-auth HTTP status (excluded from the rate, flattering an arch whose provider path failed). User decides before the sweeps. => User 2026-11-06: option A — provider errors mid-call count against the arch (PROVIDER_ERROR not emitted).
- ESCALATION(ESC-3-2) [resolved] phase=3 tier=reversible :: Both live calls (arch A, `self_correction`, unpinned worker LLM) ended `timeout` at the same point: the agent never answers the address turn ("88 Cedar Lane, Austin, TX 78701"): the user turn is committed, a preemptive generation starts, then no tool call, no reply, no error event for 3 minutes. Text mode with the same turns answers at once (so not the prompt or tools). Suspects: an LLM stream that hangs or comes back empty on the unpinned OpenRouter route (ESC-2-1), or a LiveKit preemptive-generation race. If it recurs a full sweep is mostly timeouts. User decides: investigate with LLM request logging, pin a route, or disable `preemptive_generation` in `TURN_HANDLING` before the sweeps. => Root cause (evidence from a temporary LLM/TTS/session-state diagnostic, since removed): the LLM stream ended with `text=0, tools=0, chunks=1, completion_tokens=0` (an empty completion, also on the Google-pinned route); LiveKit treats that as a finished turn, so the agent goes idle (`agent=listening`, no speech task, no error) until the caller gives up. Seen 2 of 2 diagnosed calls, always on a turn right after the caller's self-correction. Not preemptive generation (disabled in a first test: still stalled). Fixed by `llm_guard.retry_on_empty_completion` (retryable `APIConnectionError`, LiveKit's own retry, then a loud error). Also kept: preemptive generation explicitly off.
