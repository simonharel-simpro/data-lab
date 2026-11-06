"""The slices of the LiveKit STT / TTS / LLM objects the bench and the corpus use, so fakes need no network."""

from collections.abc import AsyncIterator
from typing import Protocol

from livekit import rtc
from livekit.agents import llm, stt, tts
from livekit.agents.utils import AudioBuffer


class AudioStream(Protocol):
    def __aiter__(self) -> AsyncIterator[tts.SynthesizedAudio]: ...

    async def collect(self) -> rtc.AudioFrame: ...


class Transcriber(Protocol):
    @property
    def model(self) -> str: ...

    async def recognize(self, buffer: AudioBuffer) -> stt.SpeechEvent: ...


class Synthesizer(Protocol):
    @property
    def model(self) -> str: ...

    def synthesize(self, text: str) -> AudioStream: ...


class ChatStream(Protocol):
    def __aiter__(self) -> AsyncIterator[llm.ChatChunk]: ...

    async def aclose(self) -> None: ...


class ChatModel(Protocol):
    @property
    def model(self) -> str: ...

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None) -> ChatStream: ...
