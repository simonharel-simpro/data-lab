import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_DIR.parents[1]
CORPUS_DIR = PROJECT_DIR / "data" / "corpus"
QUESTIONS_FILE = PROJECT_DIR / "data" / "questions.jsonl"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No MINI_RAG_*/DATALAB_*/MLFLOW_* from the shell, no .env from the cwd, no tracking URI left behind (F-15)."""
    for key in list(os.environ):
        if key.startswith(("MINI_RAG_", "DATALAB_", "MLFLOW_")):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    yield
    if "mlflow" in sys.modules:
        import mlflow

        # None is handled at runtime (unsets the URI); the stub omits it.
        mlflow.set_tracking_uri(None)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'mlflow.db'}"
