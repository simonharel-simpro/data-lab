import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from voice_arch.settings import VoiceSettings

LIVEKIT_SECRET = "s" * 32
PROJECT_MD = Path(__file__).resolve().parent.parent / "PROJECT.md"


def _stage1_winners() -> tuple[str, str, str]:
    """The bold rows of PROJECT.md's stage-1 table, in STT, TTS, LLM order."""
    found = re.findall(r"\*\*`([^`]+)`\*\*", PROJECT_MD.read_text())[:3]
    assert len(found) == 3
    return found[0], found[1], found[2]


def _perfect_llm_candidates() -> set[str]:
    """LLM candidates PROJECT.md scores 20/20."""
    return set(re.findall(r"`([^`]+)`\*{0,2} \| \*{0,2}20/20", PROJECT_MD.read_text()))


@pytest.fixture
def livekit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", LIVEKIT_SECRET)


def _settings() -> VoiceSettings:
    return VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]  # pydantic-settings kwarg


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

    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_URL", "ws://test.invalid:9")
    assert _settings().livekit_url == "ws://test.invalid:9"


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

    winners = _stage1_winners()
    assert s.experiment_budget_usd == 50.0  # the 50 $ software budget (plan)
    assert s.provider_list == ["google-vertex", "google-ai-studio"]  # ESC-2-1 option C
    assert s.openrouter_quantization is None  # Google endpoints report "unknown": a filter would exclude them
    assert (s.stt_model, s.tts_model, s.llm_model) == winners

    monkeypatch.setenv("VOICE_ARCH_OPENROUTER_PROVIDERS", "p-one,p-two")
    assert _settings().provider_list == ["p-one", "p-two"]


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

    assert s.caller_llm_model != s.llm_model
    assert s.caller_llm_model in _perfect_llm_candidates()


@pytest.mark.usefixtures("livekit_env")
def test_d_17_same_caller_and_agent_model_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LLM_MODEL", "x/same-model")
    monkeypatch.setenv("VOICE_ARCH_CALLER_LLM_MODEL", "x/same-model")

    with pytest.raises(ValidationError) as err:
        _settings()

    assert "D-17" in str(err.value)


@pytest.mark.usefixtures("livekit_env")
def test_call_timeout_default_covers_a_self_correction_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")

    assert _settings().call_timeout_s == 420  # a self_correction call takes 265 to 300 s


def test_agent_reasoning_effort_defaults_to_low_and_rejects_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", "s" * 32)
    # Pydantic-settings kwarg.
    assert VoiceSettings(_env_file=None).agent_reasoning_effort == "low"  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("VOICE_ARCH_AGENT_REASONING_EFFORT", "minimal")  # the value that reproduced the failure
    with pytest.raises(ValidationError):
        VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]  # pydantic-settings kwarg
