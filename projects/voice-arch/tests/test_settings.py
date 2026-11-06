import pytest
from pydantic import ValidationError

from voice_arch.settings import VoiceSettings

LIVEKIT_SECRET = "s" * 32


@pytest.fixture
def livekit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", LIVEKIT_SECRET)


def _settings() -> VoiceSettings:
    return VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


@pytest.mark.usefixtures("livekit_env")
def test_missing_openrouter_key_fails_at_settings() -> None:
    with pytest.raises(ValidationError) as err:
        _settings()

    assert "openrouter_api_key" in str(err.value).lower()


@pytest.mark.usefixtures("livekit_env")
def test_validation_error_never_echoes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-x")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_URL", "http://x")

    with pytest.raises(ValidationError) as err:
        _settings()

    assert "livekit_url" in str(err.value)
    assert "sk-or" not in str(err.value)
    assert LIVEKIT_SECRET not in str(err.value)


@pytest.mark.usefixtures("livekit_env")
def test_livekit_url_needs_ws_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_URL", "http://x")
    with pytest.raises(ValidationError):
        _settings()

    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_URL", "ws://127.0.0.1:7880")
    assert _settings().livekit_url == "ws://127.0.0.1:7880"


@pytest.mark.usefixtures("livekit_env")
def test_root_openrouter_key_is_used_when_project_key_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    assert _settings().openrouter_api_key.get_secret_value() == "k1"

    monkeypatch.setenv("VOICE_ARCH_OPENROUTER_API_KEY", "k2")
    assert _settings().openrouter_api_key.get_secret_value() == "k2"


@pytest.mark.usefixtures("livekit_env")
def test_defaults_and_provider_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")

    s = _settings()

    assert s.experiment_budget_usd == 50.0
    assert s.provider_list == ["deepinfra", "gmicloud", "parasail"]
    assert s.llm_model == "google/gemini-3.5-flash-lite"


@pytest.mark.usefixtures("livekit_env")
def test_bad_provider_slug_and_non_positive_budget_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_OPENROUTER_PROVIDERS", "Bad Slug")
    with pytest.raises(ValidationError):
        _settings()

    monkeypatch.delenv("VOICE_ARCH_OPENROUTER_PROVIDERS")
    monkeypatch.setenv("VOICE_ARCH_EXPERIMENT_BUDGET_USD", "0")
    with pytest.raises(ValidationError):
        _settings()


@pytest.mark.usefixtures("livekit_env")
def test_d_17_caller_model_default_differs_from_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")

    s = _settings()

    assert s.caller_llm_model == "anthropic/claude-haiku-5.5"
    assert s.llm_model == "google/gemini-3.5-flash-lite"


@pytest.mark.usefixtures("livekit_env")
def test_d_17_same_caller_and_agent_model_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LLM_MODEL", "x/same-model")
    monkeypatch.setenv("VOICE_ARCH_CALLER_LLM_MODEL", "x/same-model")

    with pytest.raises(ValidationError) as err:
        _settings()

    assert "D-17" in str(err.value)
