import asyncio
import json
import math
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.project import Project
from datalab.settings import Settings
from datalab.tags import Tag
from datalab.tracking import (
    _OUTCOMES,
    TrackingUnavailable,
    TrialError,
    close_runs,
    preflight,
    project_spend,
    stale_runs,
    tracked_run,
    tracked_trial,
)
from tests.conftest import REPO_ROOT


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


def test_tracking_bounds_mlflow_http_retries(sqlite_uri: str) -> None:
    preflight(sqlite_uri)

    assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "2"
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "30"


def test_tracking_keeps_a_user_retry_setting(sqlite_uri: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "5")

    preflight(sqlite_uri)

    assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "5"


def _parent(sqlite_uri: str, tmp_path: Path, name: str = "parent"):  # a context manager of the run id
    return tracked_run(_project(tmp_path), _settings(sqlite_uri), name, sub="e1")


def _children(sqlite_uri: str, parent_id: str) -> dict[str, Run]:
    client = MlflowClient(tracking_uri=sqlite_uri)
    experiment_id = client.get_run(parent_id).info.experiment_id
    runs = client.search_runs([experiment_id], filter_string=f"tags.mlflow.parentRunId = '{parent_id}'")
    return {run.info.run_name or "": run for run in runs}


def _fail(message: str):  # a context manager that raises inside the with-body
    return pytest.raises(RuntimeError, match=message)


def test_parent_logs_no_cost_usd(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with tracked_trial("a") as trial:
            trial.add_cost(0.25)
        with tracked_trial("b") as trial:
            trial.add_cost(0.5)

    assert "cost_usd" not in MlflowClient(tracking_uri=sqlite_uri).get_run(parent_id).data.metrics
    assert project_spend("p", _settings(sqlite_uri)) == 0.75


def test_f_7_failed_child_still_logs_cost_usd(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with _fail("boom"), tracked_trial("a") as trial:
            trial.add_cost(0.1)
            raise RuntimeError("boom")
        with tracked_trial("b"):
            pass

    children = _children(sqlite_uri, parent_id)
    assert (children["a"].info.status, children["a"].data.metrics["cost_usd"]) == ("FAILED", 0.1)
    assert children["b"].info.status == "FINISHED"


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

    assert project_spend("p", _settings(sqlite_uri)) == pytest.approx(0.5)


def test_project_spend_without_experiment_is_zero(sqlite_uri: str) -> None:
    with patch.object(MlflowClient, "search_runs", side_effect=AssertionError("must not be called")):
        assert project_spend("p", _settings(sqlite_uri)) == 0.0


def test_f_8_parent_lists_failed_candidates(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with tracked_trial("a"):
            pass
        with _fail("x"), tracked_trial("b"):
            raise RuntimeError("x")
    with tracked_run(_project(tmp_path), _settings(sqlite_uri), "plain", sub="e2") as plain_id:
        pass

    client = MlflowClient(tracking_uri=sqlite_uri)
    tags = client.get_run(parent_id).data.tags
    assert (tags["n_children"], tags["n_failed"], tags["failed_candidates"]) == ("2", "1", "b")
    assert _OUTCOMES == {}
    assert "n_children" not in client.get_run(plain_id).data.tags


def test_f_9_stale_runs_listed_not_closed(sqlite_uri: str) -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    client = MlflowClient(tracking_uri=sqlite_uri)
    old = _seed_run(client, "p/x", 0.0, finished=False, start_ms=int((now - timedelta(hours=48)).timestamp() * 1000))
    recent = _seed_run(client, "p/x", 0.0, finished=False, start_ms=int((now - timedelta(hours=1)).timestamp() * 1000))

    found = stale_runs("p", _settings(sqlite_uri), timedelta(hours=24), now=lambda: now)

    assert [(s.run_id, s.experiment) for s in found] == [(old, "p/x")]
    assert [client.get_run(r).info.status for r in (old, recent)] == ["RUNNING", "RUNNING"]
    with pytest.raises(ValueError, match="positive"):
        stale_runs("p", _settings(sqlite_uri), timedelta(0))


def test_f_9_close_runs_kills_only_given_ids(sqlite_uri: str) -> None:
    client = MlflowClient(tracking_uri=sqlite_uri)
    old = _seed_run(client, "p/x", 0.0, finished=False)
    other = _seed_run(client, "p/x", 0.0, finished=False)
    done = _seed_run(client, "p/x", 0.0, finished=True)

    with pytest.raises(ValueError, match=done):
        close_runs("p", _settings(sqlite_uri), [old, done])
    assert client.get_run(old).info.status == "RUNNING"

    assert close_runs("p", _settings(sqlite_uri), [old]) == [old]
    assert [client.get_run(r).info.status for r in (old, other)] == ["KILLED", "RUNNING"]


def test_f_14_child_in_parent_experiment_after_set_experiment(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        mlflow.set_experiment("other")
        with tracked_trial("a") as trial:
            pass

    client = MlflowClient(tracking_uri=sqlite_uri)
    child = client.get_run(trial.run_id)
    assert child.info.experiment_id == client.get_run(parent_id).info.experiment_id
    assert child.data.tags["mlflow.parentRunId"] == parent_id


@pytest.mark.parametrize("tag", ["project", "candidate"])
def test_f_14_trial_refuses_project_or_candidate_tag(sqlite_uri: str, tmp_path: Path, tag: str) -> None:
    with (
        _parent(sqlite_uri, tmp_path) as parent_id,
        pytest.raises(ValueError, match="override"),
        tracked_trial("a", tags={tag: "x"}),
    ):
        pass

    assert _children(sqlite_uri, parent_id) == {}


def test_trial_without_parent_refused(sqlite_uri: str) -> None:
    with pytest.raises(TrialError, match="parent"), tracked_trial("a"):
        pass


def test_u_20_tracked_trial_refuses_nested_trial(sqlite_uri: str, tmp_path: Path) -> None:
    with (
        _parent(sqlite_uri, tmp_path),
        tracked_trial("outer") as outer,
        pytest.raises(TrialError, match="outer"),
        tracked_trial("inner"),
    ):
        pass

    assert MlflowClient(tracking_uri=sqlite_uri).get_run(outer.run_id).info.status == "FINISHED"


def test_f_15_concurrent_trial_refused(sqlite_uri: str, tmp_path: Path) -> None:
    async def trial(name: str) -> None:
        with tracked_trial(name):
            await asyncio.sleep(0)

    async def both() -> list[object]:
        return await asyncio.gather(trial("a"), trial("b"), return_exceptions=True)

    with _parent(sqlite_uri, tmp_path):
        results = asyncio.run(both())

    assert [type(r) for r in results] == [type(None), TrialError]


def test_trial_slot_freed_when_cost_log_fails(sqlite_uri: str, tmp_path: Path) -> None:
    real, calls = mlflow.log_metric, []

    def flaky(*args: object, **kwargs: object) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("log failed")
        real(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    with patch("mlflow.log_metric", flaky):
        with (
            pytest.raises(OSError, match="log failed"),
            _parent(sqlite_uri, tmp_path, "first") as first_id,
            tracked_trial("a"),
        ):
            pass
        with _parent(sqlite_uri, tmp_path, "second") as second_id, tracked_trial("b"):
            pass

    client = MlflowClient(tracking_uri=sqlite_uri)
    assert client.get_run(first_id).data.tags["n_children"] == "1"
    assert client.get_run(second_id).data.tags["n_children"] == "1"


def test_u_10_trial_name_and_candidate(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with tracked_trial("hist-gb-0", candidate="hist-gb"):
            pass
        with tracked_trial("dummy"):
            pass

    children = _children(sqlite_uri, parent_id)
    assert children["hist-gb-0"].data.tags[Tag.CANDIDATE] == "hist-gb"
    assert children["dummy"].data.tags[Tag.CANDIDATE] == "dummy"


def test_add_cost_rejects_negative_and_nan(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path), tracked_trial("a") as trial:
        for bad in (-1.0, math.nan, math.inf):
            with pytest.raises(ValueError, match="cost"):
                trial.add_cost(bad)

    assert trial.cost_usd == 0.0


def test_tag_names_match_contract() -> None:
    contract = json.loads((REPO_ROOT / "contracts" / "mlflow_tags.json").read_text(encoding="utf-8"))

    assert {t.value for t in Tag} == set(contract["tags"])
    assert len(contract["tags"]) == 11
