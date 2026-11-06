---
name: voice-arch
title: "Voice agent architectures (LiveKit)"
status: en cours
tags: [voice, livekit, agents]
data: "generated US caller utterances + 6 personas"
metric:
  key: exact_rate   # an MLflow metric your runs log
  goal: max         # max | min
---

## Objectif

Pick the control architecture for a Simpro phone agent (English, US formats, appointment booking) on LiveKit:
A orchestrator, B orchestrator + state machine, C state machine + call record. Bar: at least 90 % exact bookings,
median end-to-end latency under 1.2 s, at most 50 $ spent on the whole experiment.

## Approche

1. Stage 1 bench: STT, TTS and LLM candidates compared on generated US caller utterances (accuracy, then latency);
   the winners become the defaults of `VoiceSettings`.
2. Stage 2: three architectures x 6 personas x 5 repetitions against a simulated caller.

## Enseignements

### Stage 1 (MLflow `voice-arch/bench`, 2026-11-05)

| Component | Candidate | Result | Run |
|---|---|---|---|
| STT (40 utterances, field errors / p50) | `deepgram/nova-3` | 19 errors, 0.49 s | `7a2860adf85f4984b94d8fc9de7c4106` (cost 0.070 $) |
| | **`assemblyai/universal-3-6-pro`** | **4 errors, 0.61 s** | |
| | `openai/gpt-4o-mini-transcribe` | 5 errors, 0.85 s | |
| TTS (6 lines x 3 reps, TTFB p50, round-trip judged by the STT winner) | `elevenlabs/eleven-flash-v2.5` | 0.52 s, intelligible | `9a03157e34b84c83a0c301a9523d1f3b` (cost 0.094 $) |
| | **`deepgram/aura-2`** (`aura-2-thalia-en`) | **0.38 s, intelligible** | |
| | `deepgram/flux-tts` | 0.53 s, intelligible | |
| LLM (20 tool cases, correct / TTFT p50) | `deepseek/deepseek-v4-flash` | 18/20, 1.31 s | `975a06de822f498880503bfb88cc2476` (cost 0.009 $) |
| | **`google/gemini-3.5-flash-lite`** | **20/20, 0.82 s** | |
| | `anthropic/claude-haiku-5.5` | 20/20, 1.05 s | |

Winners (the `VoiceSettings` defaults) and why:
- STT `assemblyai/universal-3-6-pro`: 4 errors, within the margin (1 error per 40) of `gpt-4o-mini-transcribe` (5), and faster
  (0.61 s vs 0.85 s). `nova-3` is fastest but 15 errors behind: it writes street numbers as words ("twelve Oak Road",
  "four fifty Maple Avenue"), which `normalize_address` does not map to digits. Without those address-number misses nova-3
  would be level with the winner on errors and win on latency: provisional, see the escalation in the Phase 1B report.
- TTS `deepgram/aura-2`: all three pass the round-trip gate, lowest TTFB.
- LLM `google/gemini-3.5-flash-lite`: ties haiku on accuracy, lower TTFT. The simulated caller's model is
  `anthropic/claude-haiku-5.5` (`caller_llm_model`, also 20/20), because D-17 says the caller is distinct from the
  agent: provisional, see ESC-1-2.
- Catalog prices are not ranked (U-9). The three runs together cost 0.17 $ of the 50 $ budget; the observed per-turn
  sum with these winners (end-of-turn 0.5 + STT 0.61 + LLM 0.82 + TTS 0.38, about 2.3 s) is above the 1.2 s bar, as the
  plan expected (#25 tracks a direct streaming STT).
- The browser smoke (audio both ways, UDP vs TCP, hand-timed turns vs `e2e_latency`) is pending, see the README; write
  its offset here.

## Suite

<!-- Next steps, or why the project stops here. -->
