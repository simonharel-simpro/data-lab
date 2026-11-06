import pytest

from voice_arch.audio import OPENROUTER, make_llm, make_stt, make_tts
from voice_arch.settings import VoiceSettings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> VoiceSettings:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", "s" * 32)
    return VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_make_llm_pins_providers_without_fallback(settings: VoiceSettings) -> None:
    llm = make_llm(settings, providers=["deepinfra", "parasail"])

    assert llm.model == "google/gemini-3.5-flash-lite"
    # pyright: private options are the only place the request preferences are visible without a network call.
    assert llm._opts.extra_body == {  # pyright: ignore[reportAttributeAccessIssue]
        "provider": {"order": ["deepinfra", "parasail"], "quantizations": ["fp8"], "allow_fallbacks": False}
    }


def test_make_llm_without_providers_sets_no_provider_preference(settings: VoiceSettings) -> None:
    llm = make_llm(settings, model="google/gemini-3.5-flash-lite")

    assert llm.model == "google/gemini-3.5-flash-lite"
    assert llm._opts.extra_body == {}  # pyright: ignore[reportAttributeAccessIssue]


def test_make_tts_uses_settings_defaults_and_pcm(settings: VoiceSettings) -> None:
    tts = make_tts(settings)

    assert (tts.model, tts._opts.voice, tts._opts.response_format) == (  # pyright: ignore[reportAttributeAccessIssue]
        "deepgram/aura-2",
        "aura-2-thalia-en",
        "pcm",
    )


def test_make_stt_model_override_and_openrouter_endpoint(settings: VoiceSettings) -> None:
    stt = make_stt(settings, "assemblyai/universal-3-6-pro")

    assert stt.model == "assemblyai/universal-3-6-pro"
    assert OPENROUTER == "https://openrouter.ai/api/v1"
    assert str(stt._client.base_url).rstrip("/") == OPENROUTER  # pyright: ignore[reportAttributeAccessIssue]
