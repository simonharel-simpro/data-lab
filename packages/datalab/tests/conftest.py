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
        mlflow.set_tracking_uri(None)  # pyright: ignore[reportArgumentType]  # None resets the URI


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
    for relative in (".pre-commit-config.yaml", ".github/workflows/ci.yml"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


@pytest.fixture
def wired_repo(fake_repo: Path) -> Path:
    """fake_repo plus the two existing projects, so the wiring parity check starts clean."""
    for name in ("mini-rag", "voice-arch"):
        (fake_repo / "projects" / name).mkdir()
        (fake_repo / "projects" / name / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return fake_repo
