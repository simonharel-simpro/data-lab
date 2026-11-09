"""STT / TTS / LLM factories: every model call goes through OpenRouter's OpenAI-compatible API (D-1, D-4)."""

from livekit.agents import NOT_GIVEN, llm, stt, tts
from livekit.plugins import openai
from openai.types import ReasoningEffort

from voice_arch.llm_guard import retry_on_empty_completion
from voice_arch.settings import VoiceSettings

OPENROUTER = "https://openrouter.ai/api/v1"


def make_stt(settings: VoiceSettings, model: str | None = None) -> stt.STT:
    """Non-streaming: `AgentSession` wraps it with its VAD automatically."""
    return openai.STT(
        model=model or settings.stt_model,
        base_url=OPENROUTER,
        api_key=settings.openrouter_api_key.get_secret_value(),
        language="en",
    )


def make_tts(settings: VoiceSettings, model: str | None = None, voice: str | None = None) -> tts.TTS:
    return openai.TTS(
        model=model or settings.tts_model,
        voice=voice or settings.tts_voice,
        base_url=OPENROUTER,
        api_key=settings.openrouter_api_key.get_secret_value(),
        response_format="pcm",
    )


def make_llm(  # noqa: PLR0913  # all options but settings are defaulted (#39)
    settings: VoiceSettings,
    model: str | None = None,
    temperature: float = 0.0,
    providers: list[str] | None = None,
    retry_empty: bool = False,
    reasoning_effort: ReasoningEffort | None = None,
) -> llm.LLM:
    """With `providers`, only those upstreams may serve it, without fallback (and at the quantization, if set).

    `reasoning_effort` is sent only when given: the caller's LLM and the bench never set it.
    """
    provider: openai.llm.OpenRouterProviderPreferences | None = None
    if providers:
        provider = {"order": providers, "allow_fallbacks": False}
        if settings.openrouter_quantization is not None:
            provider["quantizations"] = [settings.openrouter_quantization]
    model_llm = openai.LLM.with_openrouter(
        model=model or settings.llm_model,
        api_key=settings.openrouter_api_key.get_secret_value(),
        temperature=temperature,
        provider=provider,
        reasoning_effort=NOT_GIVEN if reasoning_effort is None else reasoning_effort,
    )
    return retry_on_empty_completion(model_llm, settings.dump_empty_dir) if retry_empty else model_llm


def make_agent_llm(settings: VoiceSettings) -> llm.LLM:
    """The booking agent's LLM, the same for A, B and C: pinned, retried on empty, and at a set reasoning effort.

    Without `reasoning_effort` Gemini answers a tool turn with MALFORMED_FUNCTION_CALL most of the time (see
    IMPLEMENTATION_NOTES, "Empty completion root cause"), which LiveKit reads as an empty completion.
    """
    return make_llm(
        settings,
        providers=settings.provider_list,
        retry_empty=True,
        reasoning_effort=settings.agent_reasoning_effort,
    )
