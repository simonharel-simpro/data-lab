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

<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-top:16px">
  <div class="card"><div class="muted">Stage 1 bench</div><div class="metric">done</div><div class="muted">STT, TTS, LLM winners picked (0.17 $)</div></div>
  <div class="card"><div class="muted">Live pilot (1 call per arch)</div><div class="metric" style="color:var(--warn)">A ✓ · B ✗ · C ✗</div><div class="muted">exact bookings, persona <code>self_correction</code></div></div>
  <div class="card"><div class="muted">Latency per turn (estimate)</div><div class="metric" style="color:var(--warn)">≈ 2.3 s</div><div class="muted">bar: median under 1.2 s</div></div>
  <div class="card"><div class="muted">Budget spent</div><div class="metric">≈ 0.85 $</div><div class="muted">of 50 $; the full sweeps (25 to 40 $) wait for the go</div></div>
</div>

## Objectif

Pick the control architecture for a Simpro phone agent (English, US formats, appointment booking) on
self-hosted LiveKit. Bar: at least 90 % exact bookings, median end-to-end latency under 1.2 s, at most 50 $ spent on
the whole experiment. Priority when ranking: task success, then latency, then cost (an `exact_rate` tie within 2 calls
goes to latency, then to cost).

## Approche

The three architectures share the same LLM, audio stack, instructions and tools. Only the control structure differs.

<svg viewBox="0 0 900 250" role="img" aria-label="Control structure of architectures A, B and C" style="width:100%;height:auto;color:var(--fg)">
  <style>
    .bx{fill:var(--card);stroke:var(--line);stroke-width:1.5}
    .hd{font:600 15px system-ui,sans-serif;fill:currentColor}
    .tx{font:12px system-ui,sans-serif;fill:currentColor}
    .mu{font:11px system-ui,sans-serif;fill:var(--muted)}
    .st{fill:var(--bg);stroke:var(--muted);stroke-width:1}
    .ar{stroke:var(--muted);stroke-width:1.2;fill:none;marker-end:url(#a)}
    .rec{fill:var(--warn-bg);stroke:var(--warn);stroke-width:1}
  </style>
  <defs><marker id="a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8z" fill="var(--muted)"/></marker></defs>
  <rect class="bx" x="10" y="10" width="270" height="230" rx="10"/>
  <text class="hd" x="26" y="36">A · orchestrator</text>
  <text class="mu" x="26" y="54">one Agent, every instruction and tool</text>
  <rect class="st" x="50" y="80" width="190" height="60" rx="8"/>
  <text class="tx" x="145" y="106" text-anchor="middle">Agent</text>
  <text class="mu" x="145" y="124" text-anchor="middle">can rewrite any field at any time</text>
  <text class="mu" x="26" y="180">+ simplest, one context</text>
  <text class="mu" x="26" y="198">− nothing forces the order of the steps</text>
  <rect class="bx" x="315" y="10" width="270" height="230" rx="10"/>
  <text class="hd" x="331" y="36">B · TaskGroup</text>
  <text class="mu" x="331" y="54">one AgentTask per step, going back allowed</text>
  <g class="tx" text-anchor="middle">
    <rect class="st" x="331" y="80" width="70" height="28" rx="6"/><text x="366" y="99">name</text>
    <rect class="st" x="415" y="80" width="70" height="28" rx="6"/><text x="450" y="99">phone</text>
    <rect class="st" x="499" y="80" width="70" height="28" rx="6"/><text x="534" y="99">address</text>
    <rect class="st" x="331" y="130" width="70" height="28" rx="6"/><text x="366" y="149">problem</text>
    <rect class="st" x="415" y="130" width="70" height="28" rx="6"/><text x="450" y="149">slot</text>
    <rect class="st" x="499" y="130" width="70" height="28" rx="6"/><text x="534" y="149">confirm</text>
  </g>
  <path class="ar" d="M401,94 H413"/><path class="ar" d="M485,94 H497"/>
  <path class="ar" d="M534,108 V116 H366 V128"/>
  <path class="ar" d="M401,144 H413"/><path class="ar" d="M485,144 H497"/>
  <text class="mu" x="331" y="198">+ each step has short, focused instructions</text>
  <text class="mu" x="331" y="216">− a hand-off at each step</text>
  <rect class="bx" x="620" y="10" width="270" height="230" rx="10"/>
  <text class="hd" x="636" y="36">C · B + call record</text>
  <text class="mu" x="636" y="54">the record is rendered into each step</text>
  <g class="tx" text-anchor="middle">
    <rect class="st" x="636" y="80" width="70" height="28" rx="6"/><text x="671" y="99">name</text>
    <rect class="st" x="720" y="80" width="70" height="28" rx="6"/><text x="755" y="99">phone</text>
    <rect class="st" x="804" y="80" width="70" height="28" rx="6"/><text x="839" y="99">…</text>
  </g>
  <path class="ar" d="M706,94 H718"/><path class="ar" d="M790,94 H802"/>
  <rect class="rec" x="660" y="130" width="190" height="40" rx="6"/>
  <text class="tx" x="755" y="148" text-anchor="middle">call record</text>
  <text class="mu" x="755" y="163" text-anchor="middle">filled · missing · corrections</text>
  <text class="mu" x="636" y="198">+ the agent always sees the whole booking</text>
  <text class="mu" x="636" y="216">− longer context, highest cost</text>
</svg>

1. **Stage 1 bench:** STT, TTS and LLM candidates compared on generated US caller utterances, accuracy first and then
   latency. The winners became the defaults of `VoiceSettings`.
2. **Stage 2:** 3 architectures × 6 personas × 5 repetitions (about 30 calls per architecture) against a simulated
   caller, over WebRTC on a self-hosted LiveKit server.
   - The caller is `anthropic/claude-haiku-5.5` at temperature 0.7. It must differ from the agent's model.
   - The `slot_change` persona changes the slot during the read-back.
   - The cost of a call includes the caller's STT, LLM and TTS.
   - A provider error mid-call counts against the architecture.

## Enseignements

### Stage 1: components (MLflow `voice-arch/bench`, 2026-11-05)

| Component | Candidate | Result | Run |
|---|---|---|---|
| STT (40 utterances, field errors / p50) | `deepgram/nova-3` | 19 errors, 0.49 s | `7a2860adf85f4984b94d8fc9de7c4106` (0.070 $) |
| | **`assemblyai/universal-3-6-pro`** | **4 errors, 0.61 s** | |
| | `openai/gpt-4o-mini-transcribe` | 5 errors, 0.85 s | |
| TTS (6 lines × 3 reps, TTFB p50, round-trip judged by the STT winner) | `elevenlabs/eleven-flash-v2.5` | 0.52 s, intelligible | `9a03157e34b84c83a0c301a9523d1f3b` (0.094 $) |
| | **`deepgram/aura-2`** (`aura-2-thalia-en`) | **0.38 s, intelligible** | |
| | `deepgram/flux-tts` | 0.53 s, intelligible | |
| LLM (20 tool cases, correct / TTFT p50) | `deepseek/deepseek-v4-flash` | 18/20, 1.31 s | `975a06de822f498880503bfb88cc2476` (0.009 $) |
| | **`google/gemini-3.5-flash-lite`** | **20/20, 0.82 s** | |
| | `anthropic/claude-haiku-5.5` | 20/20, 1.05 s | |

- **STT `assemblyai/universal-3-6-pro`:**
  - It is within the margin of `gpt-4o-mini-transcribe` (4 errors vs 5, the margin is 1 error per 40) and faster
    (0.61 s vs 0.85 s).
  - `nova-3` is the fastest but has 15 more errors. It writes street numbers as words ("four fifty Maple Avenue"),
    which the plan's scoring does not map to digits.
  - The scoring was kept as planned and not changed after seeing the results.
- **TTS `deepgram/aura-2`:** all three candidates pass the round-trip check; aura-2 has the lowest TTFB.
- **LLM `google/gemini-3.5-flash-lite`:** it ties haiku on accuracy, with a lower TTFT.
- **Latency per turn:** about 2.3 s (end-of-turn 0.5 + STT 0.61 + LLM 0.82 + TTS 0.38). That is above the 1.2 s bar,
  so latency is only compared between the architectures. #25 tracks a direct streaming STT.

### Live pilot: one audio call per architecture (2026-11-06)

**First, a silent stall.** The first live calls all hung after the caller gave the address: no reply, no error, just a
timeout.

- **Cause:** Gemini through OpenRouter sometimes ends a response with zero tokens. LiveKit treats an empty response as
  a finished turn, so the agent goes back to listening and says nothing.
- **How it was found:** temporary logging on the LLM stream showed `text=0, tools=0, completion_tokens=0` on the turn
  that stalled.
- **What was ruled out:** pinning a route and turning off preemptive generation did not change it.
- **Fix:** `llm_guard` makes an empty response raise a retryable error, so LiveKit sends the request again.
- **Other changes:**
  - The agent's LLM is now pinned to Google's providers (`google-vertex`, `google-ai-studio`), with no fallback.
  - Preemptive generation is off.

| Arch | Outcome | Duration | Cost | What happened |
|---|---|---|---|---|
| **A** orchestrator | ✅ exact booking | 296 s | 0.079 $ | The caller's phone correction was applied. The retry absorbed several empty responses. |
| **B** TaskGroup | ⚠️ scored, not exact | 265 s | 0.107 $ | Every field right except the phone (`512-550-0148`). Reported as an STT mishearing of the digits; not yet checked against the log. |
| **C** B + call record | ❌ timeout | 663 s | 0.137 $ | The conversation went off course and never converged. The last turn was empty on all 4 tries, and the agent fell silent. |

**What this does and does not say.** One call per architecture does not measure an architecture effect. It shows
where each one is likely to break:

- **Corrections:** with a single context, A just rewrites the field. Whether B and C keep a correction that comes
  after a step has closed is what the `self_correction` and `slot_change` personas will measure.
- **Context length:** C has the longest context and cost the most. Whether that makes Gemini drift and return empty
  responses more often is a hypothesis to test over 30 calls, not a finding.
- **Timeouts:** C's timeout, and the length of every call, show that the call length and the retry policy weigh as much
  as the architecture. The three points under "Suite" must be settled first, or the sweep will measure timeouts.

### Stage 2: full sweeps (MLflow `voice-arch/conversations`, pending)

Not run yet: they wait for the go on the budget. Once the three sweeps are FINISHED, paste the table and the decision
from `python -m voice_arch.decide` here. `cost_per_call_usd` is the cost over the same calls as `exact_rate`.

## Suite

1. **Before the sweeps (fixes, cents):**
   - Retry an empty response at a higher temperature. At temperature 0, an identical request can come back empty
     every time, as on C's last turn.
   - Guard the simulated caller's LLM the same way.
   - Raise `call_timeout_s` from 240 s to about 400 s. A `self_correction` call takes 265 to 300 s.
2. **Check B's phone error:** read the call log to tell an STT mishearing from a correction that was lost after its
   step closed.
3. **Smoke run:** `runner --arch a --personas self_correction --reps 1`.
4. **Full sweeps:** `a`, `b`, `c` one at a time (about 30 calls each, 25 to 40 $ in total), then `decide`, and the
   table above.
5. **Manual:** one browser call per architecture, rated with `rate`, plus the browser smoke (UDP vs TCP, hand-timed
   turns against `e2e_latency`).
