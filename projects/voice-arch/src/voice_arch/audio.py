"""STT / TTS / LLM factories: every model call goes through OpenRouter's OpenAI-compatible API (D-1, D-4)."""

from livekit.agents import llm, stt, tts
from livekit.plugins import openai

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


def make_llm(
    settings: VoiceSettings,
    model: str | None = None,
    temperature: float = 0.0,
    providers: list[str] | None = None,
) -> llm.LLM:
    """With `providers`, only those upstreams may serve it, at one quantization and without fallback."""
    provider: openai.llm.OpenRouterProviderPreferences | None = None
    if providers:
        provider = {
            "order": providers,
            "quantizations": [settings.openrouter_quantization],
            "allow_fallbacks": False,
        }
    return openai.LLM.with_openrouter(
        model=model or settings.llm_model,
        api_key=settings.openrouter_api_key.get_secret_value(),
        temperature=temperature,
        provider=provider,
    )
