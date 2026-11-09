import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from voice_arch.settings import VoiceSettings

_SHELL_KEYS = ("VOICE_ARCH_", "DATALAB_", "MLFLOW_", "OPENROUTER_API_KEY", "LIVEKIT_")


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No project/shell secrets or tracking URI leak into a test; no .env from the cwd."""
    for key in list(os.environ):
        if key.startswith(_SHELL_KEYS):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    yield
    if "mlflow" in sys.modules:
        import mlflow

        # None is handled at runtime (unsets the URI); the stub omits it.
        mlflow.set_tracking_uri(None)  # pyright: ignore[reportArgumentType]  # None resets the URI


@pytest.fixture
def sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'mlflow.db'}"


@pytest.fixture
def voice_settings(monkeypatch: pytest.MonkeyPatch) -> VoiceSettings:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("VOICE_ARCH_LIVEKIT_API_SECRET", "s" * 32)
    return VoiceSettings(_env_file=None)  # pyright: ignore[reportCallIssue]  # pydantic-settings kwarg
