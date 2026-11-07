import asyncio
import math
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.tags import Tag
from datalab.tracking import _OUTCOMES, TrialError, project_spend, tracked_run, tracked_trial
from tests.tracking_support import make_project, make_settings


def _parent(sqlite_uri: str, tmp_path: Path, name: str = "parent") -> AbstractContextManager[str]:
    return tracked_run(make_project(tmp_path), make_settings(sqlite_uri), name, sub="e1")


def _children(sqlite_uri: str, parent_id: str) -> dict[str, Run]:
    client = MlflowClient(tracking_uri=sqlite_uri)
    experiment_id = client.get_run(parent_id).info.experiment_id
    runs = client.search_runs([experiment_id], filter_string=f"tags.mlflow.parentRunId = '{parent_id}'")
    return {run.info.run_name or "": run for run in runs}


def _fail(message: str) -> pytest.RaisesExc[RuntimeError]:
    return pytest.raises(RuntimeError, match=message)


def test_parent_logs_no_cost_usd(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with tracked_trial("a") as trial:
            trial.add_cost(0.25)
        with tracked_trial("b") as trial:
            trial.add_cost(0.5)

    assert "cost_usd" not in MlflowClient(tracking_uri=sqlite_uri).get_run(parent_id).data.metrics
    assert project_spend("p", make_settings(sqlite_uri)) == 0.75


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


def test_f_8_parent_lists_failed_candidates(sqlite_uri: str, tmp_path: Path) -> None:
    with _parent(sqlite_uri, tmp_path) as parent_id:
        with tracked_trial("a"):
            pass
        with _fail("x"), tracked_trial("b"):
            raise RuntimeError("x")
    with tracked_run(make_project(tmp_path), make_settings(sqlite_uri), "plain", sub="e2") as plain_id:
        pass

    client = MlflowClient(tracking_uri=sqlite_uri)
    tags = client.get_run(parent_id).data.tags
    assert (tags["n_children"], tags["n_failed"], tags["failed_candidates"]) == ("2", "1", "b")
    assert _OUTCOMES == {}
    assert "n_children" not in client.get_run(plain_id).data.tags


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

    def flaky(*args: Any, **kwargs: Any) -> None:  # forwards mlflow.log_metric's own signature
        calls.append(1)
        if len(calls) == 1:
            raise OSError("log failed")
        real(*args, **kwargs)

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
