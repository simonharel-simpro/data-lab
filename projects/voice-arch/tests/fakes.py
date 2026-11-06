"""Tiny stand-ins for the STT / TTS / LLM objects: canned data, no network. Audio bytes carry the spoken text."""

import asyncio
from collections.abc import AsyncIterator, Callable

from livekit import rtc
from livekit.agents import llm, stt, tts
from livekit.agents.utils import AudioBuffer

SAMPLE_RATE = 24000


def text_frame(text: str) -> rtc.AudioFrame:
    """A frame whose PCM bytes are the text (padded to a whole int16 sample)."""
    data = text.encode("utf-8")
    data += b"\x00" * (len(data) % 2)
    return rtc.AudioFrame(data, SAMPLE_RATE, 1, len(data) // 2)


def frame_text(buffer: AudioBuffer) -> str:
    frame = buffer if isinstance(buffer, rtc.AudioFrame) else rtc.combine_audio_frames(buffer)
    return bytes(frame.data).rstrip(b"\x00").decode("utf-8")


class FakeStream:
    def __init__(self, frames: list[rtc.AudioFrame], first_delay_s: float = 0.0) -> None:
        self._frames = frames
        self._delay = first_delay_s

    def __aiter__(self) -> AsyncIterator[tts.SynthesizedAudio]:
        return self._events()

    async def _events(self) -> AsyncIterator[tts.SynthesizedAudio]:
        await asyncio.sleep(self._delay)
        for frame in self._frames:
            yield tts.SynthesizedAudio(frame=frame, request_id="fake")

    async def collect(self) -> rtc.AudioFrame:
        return rtc.combine_audio_frames([ev.frame async for ev in self])


class FakeTts:
    def __init__(
        self,
        model: str = "fake/tts",
        first_delay_s: float = 0.0,
        say: Callable[[str], str] = lambda text: text,
        silent: bool = False,
    ) -> None:
        self.model = model
        self.calls: list[str] = []
        self._delay, self._say, self._silent = first_delay_s, say, silent

    def synthesize(self, text: str) -> FakeStream:
        self.calls.append(text)
        return FakeStream([] if self._silent else [text_frame(self._say(text))], self._delay)


class FakeStt:
    def __init__(
        self,
        model: str = "fake/stt",
        hear: Callable[[str], str] = lambda spoken: spoken,
        error: Exception | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.model = model
        self.calls = 0
        self._hear, self._error, self._delay = hear, error, delay_s

    async def recognize(self, buffer: AudioBuffer) -> stt.SpeechEvent:
        self.calls += 1
        if self._error is not None:
            raise self._error
        await asyncio.sleep(self._delay)
        data = stt.SpeechData(language="en", text=self._hear(frame_text(buffer)))
        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[data])


class FakeChatStream:
    def __init__(self, chunks: list[llm.ChatChunk], first_delay_s: float) -> None:
        self._chunks, self._delay = chunks, first_delay_s

    def __aiter__(self) -> AsyncIterator[llm.ChatChunk]:
        return self._events()

    async def _events(self) -> AsyncIterator[llm.ChatChunk]:
        await asyncio.sleep(self._delay)
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


class FakeLlm:
    """`answer` maps the caller's last message to (tool name, JSON arguments); None answers with plain text."""

    def __init__(
        self,
        answer: Callable[[str], tuple[str, str] | None],
        model: str = "fake/llm",
        first_delay_s: float = 0.0,
    ) -> None:
        self.model = model
        self.calls = 0
        self._answer, self._delay = answer, first_delay_s

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None) -> FakeChatStream:
        self.calls += 1
        caller = chat_ctx.items[-1]
        text = caller.text_content if isinstance(caller, llm.ChatMessage) else ""
        call = self._answer(text or "")
        first = llm.ChatChunk(id="c0", delta=llm.ChoiceDelta(role="assistant", content=""))
        if call is None:
            return FakeChatStream([first], self._delay)
        name, arguments = call
        tool = llm.FunctionToolCall(name=name, arguments=arguments, call_id="call_1")
        return FakeChatStream([first, llm.ChatChunk(id="c1", delta=llm.ChoiceDelta(tool_calls=[tool]))], self._delay)
