import json
import os
import re
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.entities import Run, RunStatus
from mlflow.exceptions import MlflowException

from datalab.tags import Tag
from datalab.tracking import (
    TrackingUnavailable,
    close_runs,
    preflight,
    project_spend,
    stale_runs,
    tracked_run,
    tracked_trial,
)
from tests.conftest import REPO_ROOT
from tests.tracking_support import make_project, make_settings


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

    with tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r") as run_id:
        pass

    run = _only_run(sqlite_uri, "p")
    assert run.info.run_id == run_id
    assert run.data.tags["project"] == "p"


def test_project_tag_cannot_be_overridden(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        pytest.raises(ValueError, match="project"),
        tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r", tags={"project": "x"}),
    ):
        pass

    assert MlflowClient(tracking_uri=sqlite_uri).get_experiment_by_name("p") is None


def test_tracked_run_sets_project_tag_and_experiment(sqlite_uri: str, tmp_path: Path) -> None:
    with tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r", sub="bm25", tags={"step": "1"}):
        pass

    run = _only_run(sqlite_uri, "p/bm25")
    assert run.data.tags["project"] == "p"
    assert run.data.tags["step"] == "1"
    assert run.info.run_name == "r"
    assert run.info.status == "FINISHED"


def test_tracked_run_exception_marks_failed(sqlite_uri: str, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"), tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r"):
        raise RuntimeError("boom")

    assert _only_run(sqlite_uri, "p").info.status == "FAILED"


def _tagging_fails_after_project_tags() -> AbstractContextManager[object]:
    real = mlflow.set_tags

    def flaky(tags: dict[str, str], *args: Any, **kwargs: Any) -> None:  # forwards mlflow.set_tags' own signature
        if Tag.N_CHILDREN.value in tags:
            raise MlflowException("tagging down")
        real(tags, *args, **kwargs)

    return patch("mlflow.set_tags", flaky)


def test_tracked_run_surfaces_the_body_error_when_tagging_fails(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        _tagging_fails_after_project_tags(),
        pytest.raises(KeyError, match="body") as caught,
        tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r"),
    ):
        with tracked_trial("a"):
            pass
        raise KeyError("body")

    assert any("tagging the outcome failed" in note for note in caught.value.__notes__)


def test_tracked_run_still_raises_when_tagging_fails_after_a_good_body(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        _tagging_fails_after_project_tags(),
        pytest.raises(MlflowException, match="tagging down"),
        tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r"),
        tracked_trial("a"),
    ):
        pass


def _ending_as_failed_fails() -> AbstractContextManager[object]:
    real = MlflowClient.set_terminated

    def flaky(self: MlflowClient, run_id: str, status: str | None = None, end_time: int | None = None) -> None:
        if status == RunStatus.to_string(RunStatus.FAILED):
            raise MlflowException("store down")
        real(self, run_id, status, end_time)

    return patch.object(MlflowClient, "set_terminated", flaky)


def test_tracked_run_surfaces_the_body_error_when_end_run_fails(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        _ending_as_failed_fails(),
        pytest.raises(ValueError, match="body") as caught,
        tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "r"),
    ):
        raise ValueError("body")

    assert any("ending the run as FAILED failed" in note for note in caught.value.__notes__)


def test_tracked_run_after_a_failed_end_run_opens_a_top_level_run(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        _ending_as_failed_fails(),
        pytest.raises(ValueError, match="body"),
        tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "dead"),
    ):
        raise ValueError("body")

    with tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "next") as run_id:
        pass

    run = MlflowClient(tracking_uri=sqlite_uri).get_run(run_id)
    assert "mlflow.parentRunId" not in run.data.tags
    assert run.info.status == "FINISHED"


def test_preflight_unreachable_raises_tracking_unavailable() -> None:
    with pytest.raises(TrackingUnavailable, match=re.escape("127.0.0.1:9")):
        preflight("http://127.0.0.1:9")


def test_preflight_accepts_a_working_store(sqlite_uri: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # A stray shell URI, and MLflow's own default (sqlite:///mlflow.db in the cwd) equals sqlite_uri here, so only an
    # explicit set_tracking_uri can satisfy the assertion below (F-5).
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")

    preflight(sqlite_uri)  # raising here fails the test

    assert mlflow.get_tracking_uri() == sqlite_uri


def test_tracking_bounds_mlflow_http_retries(sqlite_uri: str) -> None:
    preflight(sqlite_uri)

    assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "2"
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "30"


def test_tracking_keeps_a_user_retry_setting(sqlite_uri: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "5")

    preflight(sqlite_uri)

    assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "5"


def _seed_run(
    client: MlflowClient, experiment: str, cost: float, *, finished: bool, start_ms: int | None = None
) -> str:
    exp_id = client.get_experiment_by_name(experiment)
    experiment_id = exp_id.experiment_id if exp_id is not None else client.create_experiment(experiment)
    run = client.create_run(experiment_id, start_time=start_ms, tags={"project": "p"})
    client.log_metric(run.info.run_id, "cost_usd", cost)
    if finished:
        client.set_terminated(run.info.run_id, status="FINISHED")
    return run.info.run_id


def test_f_7_budget_counts_running_runs(sqlite_uri: str) -> None:
    client = MlflowClient(tracking_uri=sqlite_uri)
    _seed_run(client, "p/x", 0.4, finished=False)
    _seed_run(client, "p/x", 0.1, finished=True)
    _seed_run(client, "p-x", 9.0, finished=True)

    assert project_spend("p", make_settings(sqlite_uri)) == pytest.approx(0.5)


def test_project_spend_without_experiment_is_zero(sqlite_uri: str) -> None:
    with patch.object(MlflowClient, "search_runs", side_effect=AssertionError("must not be called")):
        assert project_spend("p", make_settings(sqlite_uri)) == 0.0


def test_f_9_stale_runs_listed_not_closed(sqlite_uri: str) -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    client = MlflowClient(tracking_uri=sqlite_uri)
    old = _seed_run(client, "p/x", 0.0, finished=False, start_ms=int((now - timedelta(hours=48)).timestamp() * 1000))
    recent = _seed_run(client, "p/x", 0.0, finished=False, start_ms=int((now - timedelta(hours=1)).timestamp() * 1000))

    found = stale_runs("p", make_settings(sqlite_uri), timedelta(hours=24), now=lambda: now)

    assert [(s.run_id, s.experiment) for s in found] == [(old, "p/x")]
    assert [client.get_run(r).info.status for r in (old, recent)] == ["RUNNING", "RUNNING"]
    with pytest.raises(ValueError, match="positive"):
        stale_runs("p", make_settings(sqlite_uri), timedelta(0))


def test_f_9_close_runs_kills_only_given_ids(sqlite_uri: str) -> None:
    client = MlflowClient(tracking_uri=sqlite_uri)
    old = _seed_run(client, "p/x", 0.0, finished=False)
    other = _seed_run(client, "p/x", 0.0, finished=False)
    done = _seed_run(client, "p/x", 0.0, finished=True)

    with pytest.raises(ValueError, match=done):
        close_runs("p", make_settings(sqlite_uri), [old, done])
    assert client.get_run(old).info.status == "RUNNING"

    assert close_runs("p", make_settings(sqlite_uri), [old]) == [old]
    assert [client.get_run(r).info.status for r in (old, other)] == ["KILLED", "RUNNING"]


def test_tag_names_match_contract() -> None:
    contract = json.loads((REPO_ROOT / "contracts" / "mlflow_tags.json").read_text(encoding="utf-8"))

    assert {t.value for t in Tag} == set(contract["tags"])
    assert len(contract["tags"]) == 11
