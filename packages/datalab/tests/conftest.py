import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "compose.yaml").is_file())
TEMPLATE = REPO_ROOT / "templates" / "project"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No DATALAB_*/MLFLOW_* from the shell, no .env from the cwd, no tracking URI left by another test (F-15)."""
    for key in list(os.environ):
        if key.startswith(("DATALAB_", "MLFLOW_")):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    yield
    if "mlflow" in sys.modules:
        import mlflow

        # None is handled at runtime (unsets the URI and the MLFLOW_TRACKING_URI it exports); the stub omits it.
        mlflow.set_tracking_uri(None)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'mlflow.db'}"


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A repo-shaped tree below tmp_path (so a stray card can sit above it) with the real template + decoys."""
    root = tmp_path / "repo"
    (root / "packages" / "datalab").mkdir(parents=True)
    (root / "projects").mkdir()
    (root / "compose.yaml").write_text("name: fake\n", encoding="utf-8")
    template = root / "templates" / "project"
    shutil.copytree(TEMPLATE, template)
    (template / ".venv" / "bin").mkdir(parents=True)
    (template / ".venv" / "bin" / "python").write_text("decoy\n", encoding="utf-8")
    (template / ".env").write_text("DATALAB_MLFLOW_TRACKING_URI=http://decoy\n", encoding="utf-8")
    (template / "uv.lock").write_text("decoy\n", encoding="utf-8")
    return root
