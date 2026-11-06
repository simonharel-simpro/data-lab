"""The simulated caller: an `AgentSession` that plays one persona and never speaks first (F-8, U-20)."""

from typing import Final, Protocol

from livekit.agents import Agent, AgentSession, llm
from livekit.plugins import silero

from voice_arch.audio import make_llm, make_stt, make_tts
from voice_arch.settings import VoiceSettings
from voice_arch.worker_logic import TURN_HANDLING

NEVER_SPEAK_FIRST: Final = "Never speak first."


class LlmFactory(Protocol):
    def __call__(self, settings: VoiceSettings, *, model: str, temperature: float) -> llm.LLM: ...


class CallerAgent(Agent):
    """No `on_enter`: the booking agent greets and asks first, the caller only answers."""

    def __init__(self, persona_instructions: str) -> None:
        super().__init__(instructions=f"{persona_instructions} {NEVER_SPEAK_FIRST}")


def make_caller_session(settings: VoiceSettings, llm_factory: LlmFactory = make_llm) -> AgentSession[None]:
    """Same audio stack and turn handling as the worker; the LLM is the configured caller model (D-17)."""
    return AgentSession[None](
        stt=make_stt(settings),
        llm=llm_factory(settings, model=settings.caller_llm_model, temperature=settings.caller_temperature),
        tts=make_tts(settings),
        vad=silero.VAD.load(),
        turn_handling=TURN_HANDLING,
    )
