import re

import pytest
from pydantic import ValidationError

from mini_rag.settings import PilotSettings, public_url

_KEY = "sk-or-test"


def test_f_13_missing_llm_api_key_fails_at_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINI_RAG_LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="MINI_RAG_LLM_API_KEY is required for OpenRouter"):
        PilotSettings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def test_api_key_is_masked_in_repr() -> None:
    pilot = PilotSettings(_env_file=None, llm_api_key=_KEY)  # type: ignore[call-arg]

    assert _KEY not in repr(pilot)
    assert pilot.llm_api_key is not None
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
    monkeypatch.setenv("MINI_RAG_LLM_BASE_URL", "https://eu.openrouter.ai/api")
    monkeypatch.setenv("MINI_RAG_LLM_API_KEY", _KEY)
    monkeypatch.setenv("GEN_MODEL", "wrong-model")
    if prefixed_model is None:
        monkeypatch.delenv("MINI_RAG_GEN_MODEL", raising=False)
    else:
        monkeypatch.setenv("MINI_RAG_GEN_MODEL", prefixed_model)

    pilot = PilotSettings(_env_file=None)  # type: ignore[call-arg]

    assert pilot.llm_base_url == "https://eu.openrouter.ai/api"
    assert pilot.gen_model == expected_model


def test_scheme_less_llm_url_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url="dgx.lan:8000", gen_model="m")  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://", "://", "garbage://", "x ://y", "http:// host"])
def test_malformed_llm_url_fails_at_settings(url: str) -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url=url, gen_model="m")  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://dgx.lan:8000", "https://openrouter.ai/api"])
def test_llm_url_with_scheme_and_host_validates(url: str) -> None:
    pilot = PilotSettings(_env_file=None, llm_api_key=_KEY, llm_base_url=url, gen_model="m")  # type: ignore[call-arg]

    assert pilot.llm_base_url == url


def test_unprefixed_llm_api_key_is_not_picked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINI_RAG_LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "another-tools-key")

    with pytest.raises(ValidationError, match="MINI_RAG_LLM_API_KEY is required"):
        PilotSettings(_env_file=None)  # type: ignore[call-arg]


def test_dgx_needs_no_key_when_the_model_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINI_RAG_LLM_API_KEY", raising=False)

    pilot = PilotSettings(_env_file=None, llm_base_url="http://dgx.lan:8000", gen_model="deepseek-v4-flash")  # type: ignore[call-arg]

    assert pilot.llm_api_key is None


def test_non_openrouter_endpoint_refuses_the_openrouter_default_model() -> None:
    with pytest.raises(ValidationError, match=re.escape("set MINI_RAG_GEN_MODEL for http://dgx.lan:8000")):
        PilotSettings(_env_file=None, llm_base_url="http://dgx.lan:8000")  # type: ignore[call-arg]


def test_legacy_dgx_base_url_is_refused_not_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_RAG_DGX_BASE_URL", "http://dgx.lan:8000")

    with pytest.raises(ValidationError, match="MINI_RAG_DGX_BASE_URL was renamed"):
        PilotSettings(_env_file=None, llm_api_key=_KEY)  # type: ignore[call-arg]


def test_legacy_dgx_base_url_in_env_file_is_refused(tmp_path: pytest.TempPathFactory) -> None:
    env = tmp_path / ".env"  # type: ignore[operator]
    env.write_text("MINI_RAG_DGX_BASE_URL=http://dgx.lan:8000\nMINI_RAG_LLM_API_KEY=k\n")

    with pytest.raises(ValidationError, match="MINI_RAG_DGX_BASE_URL was renamed"):
        PilotSettings(_env_file=env)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("url", "logged"),
    [
        ("https://openrouter.ai/api", "https://openrouter.ai/api"),
        ("https://user:tok@proxy.example:8443/api?key=s3cret#x", "https://proxy.example:8443/api"),
        ("http://172.16.0.5:8000", "http://172.16.0.5:8000"),
    ],
)
def test_public_url_drops_credentials_query_and_fragment(url: str, logged: str) -> None:
    assert public_url(url) == logged


def test_validation_error_never_echoes_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_RAG_DGX_BASE_URL", "http://dgx.lan:8000")

    with pytest.raises(ValidationError) as err:
        PilotSettings(_env_file=None, llm_api_key="sk-or-v1-very-secret")  # type: ignore[call-arg]

    assert "sk-or" not in str(err.value)


@pytest.mark.parametrize("bad", ["Deep Infra", "a,,b", "a;b"])
def test_provider_list_must_be_slugs(bad: str) -> None:
    with pytest.raises(ValidationError, match="provider slugs"):
        PilotSettings(_env_file=None, llm_api_key=_KEY, openrouter_providers=bad)  # type: ignore[call-arg]


def test_provider_list_is_trimmed_and_ordered() -> None:
    pilot = PilotSettings(_env_file=None, llm_api_key=_KEY, openrouter_providers=" deepinfra , parasail ")  # type: ignore[call-arg]

    assert pilot.provider_list == ["deepinfra", "parasail"]
