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

## Escalations
- ESCALATION(ESC-1-1) [resolved] phase=1 tier=reversible :: STT winner depends on address number scoring: nova-3 writes street numbers as words (15 of its 19 errors); normalize_address maps no number words. Option A keep plan scoring (assemblyai wins) / B add number-word mapping and re-run (nova-3 likely wins on latency). => Kept the plan's U-4 scoring (option A): normalize_address is specified without number words, and changing scoring after seeing results would bias the bench. assemblyai/universal-3-6-pro stays the STT winner. Revisit if Phase 2 exact-booking fails on number-word addresses.
- ESCALATION(ESC-1-2) [open] phase=1 tier=reversible :: LLM bench winner google/gemini-3.5-flash-lite equals the caller model default, but D-17 requires caller != agent. Provisional: agent = gemini-3.5-flash-lite (bench winner), caller = anthropic/claude-haiku-5.5 (also 20/20) at temperature 0.7. User to confirm which model plays the caller.

