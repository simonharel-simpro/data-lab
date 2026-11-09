import pytest
from livekit.agents import llm

from voice_arch.audio import make_agent_llm, make_llm, make_stt, make_tts
from voice_arch.settings import VoiceSettings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> VoiceSettings:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", "s" * 32)
    monkeypatch.setenv("VOICE_ARCH_LLM_MODEL", "test/llm-x")
    monkeypatch.setenv("VOICE_ARCH_TTS_MODEL", "test/tts-x")
    monkeypatch.setenv("VOICE_ARCH_TTS_VOICE", "test-voice")
    monkeypatch.setenv("VOICE_ARCH_STT_MODEL", "test/stt-x")
    return VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_make_llm_pins_providers_without_fallback_or_quantization(settings: VoiceSettings) -> None:
    llm = make_llm(settings, providers=["prov-a", "prov-b"])

    assert llm.model == "test/llm-x"
    # Private options are the only place the request preferences are visible without a network call.
    assert llm._opts.extra_body == {  # pyright: ignore[reportAttributeAccessIssue]
        "provider": {"order": ["prov-a", "prov-b"], "allow_fallbacks": False}
    }


def test_make_llm_adds_quantizations_only_when_configured(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOICE_ARCH_OPENROUTER_QUANTIZATION", "test-quant")
    quantized = VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]

    llm = make_llm(quantized, providers=["prov-a"])

    assert llm._opts.extra_body == {  # pyright: ignore[reportAttributeAccessIssue]
        "provider": {"order": ["prov-a"], "quantizations": ["test-quant"], "allow_fallbacks": False}
    }


def test_make_llm_without_providers_sets_no_provider_preference(settings: VoiceSettings) -> None:
    llm = make_llm(settings, model="test/override-llm")

    assert llm.model == "test/override-llm"
    assert llm._opts.extra_body == {}  # pyright: ignore[reportAttributeAccessIssue]


def test_make_tts_uses_settings_defaults_and_pcm(settings: VoiceSettings) -> None:
    tts = make_tts(settings)

    assert (tts.model, tts._opts.voice, tts._opts.response_format) == (  # pyright: ignore[reportAttributeAccessIssue]
        "test/tts-x",
        "test-voice",
        "pcm",
    )


def test_make_stt_model_override_and_openrouter_endpoint(settings: VoiceSettings) -> None:
    stt = make_stt(settings, "test/override-stt")

    assert stt.model == "test/override-stt"
    # Documented OpenRouter API root (not the module constant).
    base = stt._client.base_url  # pyright: ignore[reportAttributeAccessIssue]
    assert (base.scheme, base.host, base.path.rstrip("/")) == ("https", "openrouter.ai", "/api/v1")
    assert make_stt(settings).model == "test/stt-x"  # pyright: ignore[reportAttributeAccessIssue]


async def test_make_llm_sends_reasoning_effort_only_when_asked(settings: VoiceSettings) -> None:
    plain = make_llm(settings).chat(chat_ctx=llm.ChatContext())
    asked = make_llm(settings, reasoning_effort="low").chat(chat_ctx=llm.ChatContext())
    await plain.aclose()
    await asked.aclose()  # both cancelled before their first await: nothing is sent

    assert "reasoning_effort" not in plain._extra_kwargs  # pyright: ignore[reportAttributeAccessIssue]
    assert asked._extra_kwargs["reasoning_effort"] == "low"  # pyright: ignore[reportAttributeAccessIssue]


async def test_agent_llm_is_pinned_retried_and_at_low_reasoning(settings: VoiceSettings) -> None:
    """The ESC-3-2 root cause: with no reasoning effort Gemini emits MALFORMED_FUNCTION_CALL on tool turns."""
    model = make_agent_llm(settings)

    stream = model.chat(chat_ctx=llm.ChatContext())
    await stream.aclose()

    extra = stream._extra_kwargs  # pyright: ignore[reportAttributeAccessIssue]
    assert extra["reasoning_effort"] == "low"
    assert extra["extra_body"]["provider"]["order"] == ["google-vertex", "google-ai-studio"]
    assert model.chat.__name__ == "guarded_chat"
