import re
from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.project import Project
from datalab.settings import Settings
from datalab.tracking import TrackingUnavailable, preflight, tracked_run


def _project(tmp_path: Path) -> Project:
    return Project(name="p", root=tmp_path)


def _settings(sqlite_uri: str) -> Settings:
    return Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def _only_run(sqlite_uri: str, experiment: str) -> Run:
    client = MlflowClient(tracking_uri=sqlite_uri)
    exp = client.get_experiment_by_name(experiment)
    assert exp is not None, f"experiment {experiment!r} not in {sqlite_uri}"
    (run,) = client.search_runs([exp.experiment_id])
    return run


def test_f_5_tracked_run_uses_settings_uri_not_env(
    sqlite_uri: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")

    with tracked_run(_project(tmp_path), _settings(sqlite_uri), "r") as run_id:
        pass

    run = _only_run(sqlite_uri, "p")
    assert run.info.run_id == run_id
    assert run.data.tags["project"] == "p"


def test_project_tag_cannot_be_overridden(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        pytest.raises(ValueError, match="project"),
        tracked_run(_project(tmp_path), _settings(sqlite_uri), "r", tags={"project": "x"}),
    ):
        pass

    assert MlflowClient(tracking_uri=sqlite_uri).get_experiment_by_name("p") is None


def test_tracked_run_sets_project_tag_and_experiment(sqlite_uri: str, tmp_path: Path) -> None:
    with tracked_run(_project(tmp_path), _settings(sqlite_uri), "r", sub="bm25", tags={"step": "1"}):
        pass

    run = _only_run(sqlite_uri, "p/bm25")
    assert run.data.tags["project"] == "p"
    assert run.data.tags["step"] == "1"
    assert run.info.run_name == "r"
    assert run.info.status == "FINISHED"


def test_tracked_run_exception_marks_failed(sqlite_uri: str, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"), tracked_run(_project(tmp_path), _settings(sqlite_uri), "r"):
        raise RuntimeError("boom")

    assert _only_run(sqlite_uri, "p").info.status == "FAILED"


def test_preflight_unreachable_raises_tracking_unavailable() -> None:
    with pytest.raises(TrackingUnavailable, match=re.escape("127.0.0.1:9")):
        preflight("http://127.0.0.1:9")


def test_preflight_accepts_a_working_store(sqlite_uri: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # A stray shell URI, and MLflow's own default (sqlite:///mlflow.db in the cwd) equals sqlite_uri here, so only an
    # explicit set_tracking_uri can satisfy the assertion below (F-5).
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")

    preflight(sqlite_uri)  # raising here fails the test

    assert mlflow.get_tracking_uri() == sqlite_uri
