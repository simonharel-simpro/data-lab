import pytest
from pydantic import ValidationError

from mini_rag.settings import PilotSettings


def test_f_13_missing_dgx_base_url_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="dgx_base_url"):
        PilotSettings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


@pytest.mark.parametrize(
    ("prefixed_model", "expected_model"),
    [("prefixed-model", "prefixed-model"), (None, PilotSettings.model_fields["gen_model"].default)],
    ids=["prefixed-wins", "unprefixed-ignored"],
)
def test_settings_read_only_the_mini_rag_prefix(
    monkeypatch: pytest.MonkeyPatch, prefixed_model: str | None, expected_model: str
) -> None:
    monkeypatch.setenv("DGX_BASE_URL", "http://wrong.invalid")
    monkeypatch.setenv("MINI_RAG_DGX_BASE_URL", "http://dgx.invalid:8000")
    monkeypatch.setenv("GEN_MODEL", "wrong-model")
    if prefixed_model is None:
        monkeypatch.delenv("MINI_RAG_GEN_MODEL", raising=False)
    else:
        monkeypatch.setenv("MINI_RAG_GEN_MODEL", prefixed_model)

    pilot = PilotSettings(_env_file=None)  # type: ignore[call-arg]

    assert pilot.dgx_base_url == "http://dgx.invalid:8000"
    assert pilot.gen_model == expected_model


def test_scheme_less_dgx_url_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, dgx_base_url="dgx.lan:8000")  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://", "://", "garbage://", "x ://y", "http:// host"])
def test_malformed_dgx_url_fails_at_settings(url: str) -> None:
    with pytest.raises(ValidationError, match="scheme"):
        PilotSettings(_env_file=None, dgx_base_url=url)  # type: ignore[call-arg]


@pytest.mark.parametrize("url", ["http://dgx.lan:8000", "https://dgx.example/v1"])
def test_dgx_url_with_scheme_and_host_validates(url: str) -> None:
    assert PilotSettings(_env_file=None, dgx_base_url=url).dgx_base_url == url  # type: ignore[call-arg]
