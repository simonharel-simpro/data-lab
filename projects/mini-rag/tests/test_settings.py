import pytest
from pydantic import ValidationError

from mini_rag.settings import PilotSettings


def test_f_13_missing_dgx_base_url_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="dgx_base_url"):
        PilotSettings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def test_settings_read_only_the_mini_rag_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGX_BASE_URL", "http://wrong.invalid")
    monkeypatch.setenv("MINI_RAG_DGX_BASE_URL", "http://dgx.invalid:8000")

    pilot = PilotSettings(_env_file=None)  # type: ignore[call-arg]

    assert pilot.dgx_base_url == "http://dgx.invalid:8000"
    assert (pilot.gen_model, pilot.gen_timeout_s, pilot.max_tokens) == ("deepseek-v4-flash", 60, 512)
