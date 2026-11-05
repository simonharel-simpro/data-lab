import pytest
from pydantic import ValidationError

from mini_rag.settings import PilotSettings

_KEY = "sk-or-test"


def test_f_13_missing_llm_api_key_fails_at_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINI_RAG_LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="llm_api_key"):
        PilotSettings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def test_api_key_is_masked_in_repr() -> None:
    pilot = PilotSettings(_env_file=None, llm_api_key=_KEY)  # type: ignore[call-arg]

    assert _KEY not in repr(pilot)
    assert pilot.llm_api_key.get_secret_value() == _KEY


@pytest.mark.parametrize(
    ("prefixed_model", "expected_model"),
    [("prefixed-model", "prefixed-model"), (None, PilotSettings.model_fields["gen_model"].default)],
    ids=["prefixed-wins", "unprefixed-ignored"],
)
def test_settings_read_only_the_mini_rag_prefix(
    monkeypatch: pytest.MonkeyPatch, prefixed_model: str | None, expected_model: str
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://wrong.invalid")
    monkeypatch.setenv("MINI_RAG_LLM_BASE_URL", "http://dgx.invalid:8000")
    monkeypatch.setenv("MINI_RAG_LLM_API_KEY", _KEY)
    monkeypatch.setenv("GEN_MODEL", "wrong-model")
    if prefixed_model is None:
        monkeypatch.delenv("MINI_RAG_GEN_MODEL", raising=False)
    else:
        monkeypatch.setenv("MINI_RAG_GEN_MODEL", prefixed_model)

    pilot = PilotSettings(_env_file=None)  # type: ignore[call-arg]

    assert pilot.llm_base_url == "http://dgx.invalid:8000"
    assert pilot.gen_model == expected_model


def test_scheme_less_llm_url_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url="dgx.lan:8000")  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://", "://", "garbage://", "x ://y", "http:// host"])
def test_malformed_llm_url_fails_at_settings(url: str) -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url=url)  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://dgx.lan:8000", "https://openrouter.ai/api"])
def test_llm_url_with_scheme_and_host_validates(url: str) -> None:
    pilot = PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url=url)  # type: ignore[call-arg]

    assert pilot.llm_base_url == url
