"""The three stage-1 measurements. They take STT / TTS / LLM objects, not settings, so fakes can stand in."""

import json
import statistics
import time
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livekit import rtc
from livekit.agents import llm

from voice_arch.corpus import Corpus, Utterance
from voice_arch.fields import args_correct, field_errors
from voice_arch.seams import AudioStream, ChatModel, Synthesizer, Transcriber
from voice_arch.tool_schemas import to_raw_tools
from voice_arch.winners import LlmRow, SttRow, TtsRow

_SYSTEM: Final = (
    "You are a phone booking agent. Call exactly one tool that records what the caller just said. "
    "Never answer with text."
)


@dataclass(frozen=True)
class LlmCase:
    id: str
    caller: str
    expected_tool: str
    expected_args: Mapping[str, str]


def load_llm_cases(path: Path) -> list[LlmCase]:
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return [LlmCase(r["id"], r["caller"], r["expected_tool"], r["expected_args"]) for r in rows]


def read_wav(path: Path) -> rtc.AudioFrame:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        return rtc.AudioFrame(wav.readframes(frames), wav.getframerate(), wav.getnchannels(), frames)


def _p50(values: list[float]) -> float:
    return statistics.median(values)


async def _transcribe(model: Transcriber, frame: rtc.AudioFrame) -> tuple[str, float]:
    start = time.perf_counter()
    event = await model.recognize(frame)
    elapsed = time.perf_counter() - start
    return (event.alternatives[0].text if event.alternatives else ""), elapsed


async def run_stt(stts: Mapping[str, Transcriber], corpus: Corpus, utterances: list[Utterance]) -> list[SttRow]:
    """Errors = wrong fields over every utterance; a call error (402 included) propagates and aborts the bench."""
    rows: list[SttRow] = []
    for name, model in stts.items():
        errors, latencies = 0, []
        for utterance in utterances:
            text, elapsed = await _transcribe(model, read_wav(corpus.paths[utterance.id]))
            latencies.append(elapsed)
            errors += sum(field_errors(text, utterance.truth).values())
        rows.append(SttRow(name, errors, len(utterances), _p50(latencies)))
    return rows


async def _speak(model: Synthesizer, line: str) -> tuple[rtc.AudioFrame, float]:
    """The synthesised line and the time to its first frame."""
    start = time.perf_counter()
    stream: AudioStream = model.synthesize(line)
    frames: list[rtc.AudioFrame] = []
    ttfb = 0.0
    async for event in stream:
        if not frames:
            ttfb = time.perf_counter() - start
        frames.append(event.frame)
    return rtc.combine_audio_frames(frames), ttfb


async def run_tts(
    ttss: Mapping[str, Synthesizer], lines: list[str], judge_stt: Transcriber, reps: int = 3
) -> list[TtsRow]:
    """Intelligible = the judge STT hears every line back; only the first rep of a line is judged (cost)."""
    rows: list[TtsRow] = []
    for name, model in ttss.items():
        ttfbs, heard_ok = [], True
        for line in lines:
            for rep in range(reps):
                frame, ttfb = await _speak(model, line)
                ttfbs.append(ttfb)
                if rep == 0:
                    text, _ = await _transcribe(judge_stt, frame)
                    heard_ok = heard_ok and not any(field_errors(text, {"line": line}).values())
        rows.append(TtsRow(name, _p50(ttfbs), heard_ok))
    return rows


def _tool_calls(chunks: list[llm.ChatChunk]) -> list[llm.FunctionToolCall]:
    return [call for chunk in chunks if chunk.delta for call in chunk.delta.tool_calls]


def _is_correct(case: LlmCase, calls: list[llm.FunctionToolCall]) -> bool:
    if len(calls) != 1 or calls[0].name != case.expected_tool:
        return False
    try:
        args = json.loads(calls[0].arguments)
    except ValueError:
        return False
    return isinstance(args, dict) and args_correct(args, case.expected_args)


async def _ask(model: ChatModel, case: LlmCase) -> tuple[bool, float]:
    ctx = llm.ChatContext()
    ctx.add_message(role="system", content=_SYSTEM)
    ctx.add_message(role="user", content=case.caller)
    start = time.perf_counter()
    stream = model.chat(chat_ctx=ctx, tools=[*to_raw_tools()])
    chunks: list[llm.ChatChunk] = []
    ttft = 0.0
    try:
        async for chunk in stream:
            if not chunks:
                ttft = time.perf_counter() - start
            chunks.append(chunk)
    finally:
        await stream.aclose()
    return _is_correct(case, _tool_calls(chunks)), ttft


async def run_llm(llms: Mapping[str, ChatModel], cases: list[LlmCase]) -> list[LlmRow]:
    rows: list[LlmRow] = []
    for name, model in llms.items():
        results = [await _ask(model, case) for case in cases]
        rows.append(LlmRow(name, sum(ok for ok, _ in results), len(cases), _p50([t for _, t in results])))
    return rows
