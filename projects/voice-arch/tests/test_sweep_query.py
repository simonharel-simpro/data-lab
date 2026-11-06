from pathlib import Path

import pytest
from mlflow import MlflowClient

from voice_arch.arch import Arch
from voice_arch.decide import SweepDataError, summary_from_metrics
from voice_arch.sweep_query import human_ratings, last_full_sweep_cost, latest_full_metrics


def _run(
    client: MlflowClient, experiment_id: str, start: int, status: str, metrics: dict[str, float], **tags: str
) -> None:
    run = client.create_run(experiment_id, start_time=start, tags=tags)
    for key, value in metrics.items():
        client.log_metric(run.info.run_id, key, value)
    client.set_terminated(run.info.run_id, status=status)


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> MlflowClient:
    """One migrated sqlite store for the module (a fresh one costs ~7 s): runs of three archs plus noise."""
    mlflow = MlflowClient(f"sqlite:///{tmp_path_factory.mktemp('sweeps') / 'mlflow.db'}")
    conv = mlflow.create_experiment("voice-arch/conversations")
    human = mlflow.create_experiment("voice-arch/human")
    _run(mlflow, conv, 1000, "FINISHED", {"cost_usd": 3.0, "n_exact": 20}, full="true", arch="a")
    _run(mlflow, conv, 2000, "FINISHED", {"cost_usd": 4.0, "n_exact": 25, "n_scored": 30}, full="true", arch="a")
    _run(mlflow, conv, 3000, "FINISHED", {"cost_usd": 9.0, "smoke_n_exact": 1}, full="false", arch="b")
    _run(mlflow, conv, 4000, "FAILED", {"cost_usd": 8.0, "n_exact": 30}, full="true", arch="b")
    _run(mlflow, human, 5000, "FINISHED", {"human_rating": 4.0}, source="human", arch="a")
    _run(mlflow, human, 6000, "FINISHED", {"human_rating": 2.0}, source="human", arch="a")
    _run(mlflow, human, 7000, "FINISHED", {"human_rating": 5.0}, source="human", arch="c")
    return mlflow


def test_last_full_sweep_cost_is_the_newest_finished_full_run(client: MlflowClient) -> None:
    assert last_full_sweep_cost(client) == pytest.approx(4.0)


def test_last_full_sweep_cost_without_experiment_is_none(tmp_path: Path) -> None:
    assert last_full_sweep_cost(MlflowClient(f"sqlite:///{tmp_path / 'empty.db'}")) is None


def test_latest_full_metrics_has_only_archs_with_a_finished_full_run(client: MlflowClient) -> None:
    found = latest_full_metrics(client)

    assert set(found) == {Arch.A}
    assert found[Arch.A]["n_exact"] == 25


def test_human_ratings_are_per_arch(client: MlflowClient) -> None:
    assert sorted(human_ratings(client, Arch.A)) == [2, 4]
    assert human_ratings(client, Arch.B) == []


def test_summary_counts_calls_from_the_outcome_metrics() -> None:
    metrics = {"n_exact": 25.0, "n_scored": 26.0, "n_timeout": 3.0, "n_agent_lost": 1.0, "latency_p50_s": 1.9}

    summary = summary_from_metrics(Arch.B, metrics, [4, 5, 3])

    assert (summary.exact, summary.n, summary.latency_p50_s) == (25, 30, 1.9)
    assert summary.cost_per_call_usd is None
    assert summary.human_rating_mean == 4.0


def test_summary_of_a_run_without_outcome_metrics_is_refused() -> None:
    with pytest.raises(SweepDataError, match="n_scored"):
        summary_from_metrics(Arch.A, {"n_exact": 1.0}, [])
