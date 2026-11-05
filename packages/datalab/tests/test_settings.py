import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from datalab.settings import Settings
from tests.conftest import REPO_ROOT


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def _parse_env(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line.strip() and not line.startswith("#"))


def _env_example() -> dict[str, str]:
    return _parse_env(REPO_ROOT / ".env.example")


def _compose_host_ports() -> dict[tuple[str, int], tuple[str, int]]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not on PATH: the compose part of the parity check cannot run")
    # Fixed argv, absolute binary, no shell: nothing user-controlled reaches the command line.
    result = subprocess.run(  # noqa: S603
        [docker, "compose", "-f", str(REPO_ROOT / "compose.yaml"), "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    return {
        (name, int(p["target"])): (p["host_ip"], int(p["published"]))
        for name, svc in services.items()
        for p in svc.get("ports", [])
        if p.get("published") is not None
    }


def test_f_5_settings_ignores_bare_mlflow_tracking_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    assert _settings().mlflow_tracking_uri == _env_example()["DATALAB_MLFLOW_TRACKING_URI"]

    monkeypatch.setenv("DATALAB_MLFLOW_TRACKING_URI", "http://x:1")
    assert _settings().mlflow_tracking_uri == "http://x:1"


def test_settings_reads_dotenv_from_cwd(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DATALAB_WEAVIATE_HTTP_PORT=9999\nDATALAB_WEAVIATE_GRPC_PORT=\n", encoding="utf-8")

    settings = Settings()

    assert settings.weaviate_http_port == 9999
    assert settings.weaviate_grpc_port == 50052  # empty value ignored, default kept


def test_g_10_ports_agree_everywhere() -> None:
    s = _settings()
    uri = urlsplit(s.mlflow_tracking_uri)
    from_settings = (s.weaviate_host, s.weaviate_http_port, s.weaviate_grpc_port, uri.hostname, uri.port)
    env = _env_example()
    env_uri = urlsplit(env["DATALAB_MLFLOW_TRACKING_URI"])
    from_env = (
        env["DATALAB_WEAVIATE_HOST"],
        int(env["DATALAB_WEAVIATE_HTTP_PORT"]),
        int(env["DATALAB_WEAVIATE_GRPC_PORT"]),
        env_uri.hostname,
        env_uri.port,
    )
    assert from_settings == from_env == ("127.0.0.1", 8090, 50052, "127.0.0.1", 5050)


def test_g_10_env_examples_agree() -> None:
    copies = [
        REPO_ROOT / ".env.example",
        REPO_ROOT / "templates" / "project" / ".env.example",
        REPO_ROOT / "projects" / "mini-rag" / ".env.example",
    ]

    shared = [{k: v for k, v in _parse_env(path).items() if k.startswith("DATALAB_")} for path in copies]

    assert shared[0], "the root .env.example defines no DATALAB_* key"
    assert shared[1] == shared[0]
    assert shared[2] == shared[0]


def test_g_10_ports_agree_with_compose() -> None:
    ports = _compose_host_ports()
    assert ports[("weaviate", 8080)] == ("127.0.0.1", 8090)
    assert ports[("weaviate", 50051)] == ("127.0.0.1", 50052)
    assert ports[("mlflow", 5000)] == ("127.0.0.1", 5050)


def test_scheme_less_tracking_uri_fails_at_settings() -> None:
    with pytest.raises(ValidationError, match="scheme"):
        Settings(_env_file=None, mlflow_tracking_uri="127.0.0.1:5050")  # type: ignore[call-arg]


def test_sqlite_tracking_uri_still_validates(tmp_path: Path) -> None:
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"

    assert Settings(_env_file=None, mlflow_tracking_uri=uri).mlflow_tracking_uri == uri  # type: ignore[call-arg]


@pytest.mark.parametrize("uri", ["http://", "://", "garbage://", "x ://y", "http:// host"])
def test_malformed_tracking_uri_fails_at_settings(uri: str) -> None:
    with pytest.raises(ValidationError, match="scheme"):
        Settings(_env_file=None, mlflow_tracking_uri=uri)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "uri",
    ["sqlite:////abs/mlflow.db", "sqlite:///rel.db", "postgresql://u@h/db", "mysql://u@h:3306/db", "http://h:5000"],
)
def test_valid_tracking_uri_schemes_still_validate(uri: str) -> None:
    assert Settings(_env_file=None, mlflow_tracking_uri=uri).mlflow_tracking_uri == uri  # type: ignore[call-arg]
