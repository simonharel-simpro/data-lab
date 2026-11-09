from datetime import UTC, datetime

import pytest
from mlflow import MlflowClient

from datalab.settings import Settings
from voice_arch.budget import ESTIMATES_USD, BudgetExceeded, check_budget, spent_so_far


def _settings(sqlite_uri: str) -> Settings:
    return Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)  # type: ignore[call-arg]  # pydantic-settings kwarg


def _run(client: MlflowClient, experiment_id: str, cost: float | None, status: str | None = "FINISHED") -> str:
    """A run tagged like `tracked_run` does; `status=None` leaves it RUNNING."""
    run = client.create_run(experiment_id, tags={"project": "voice-arch"})
    if cost is not None:
        client.log_metric(run.info.run_id, "cost_usd", cost, int(datetime.now(UTC).timestamp() * 1000))
    if status is not None:
        client.set_terminated(run.info.run_id, status=status)
    return run.info.run_id


def test_spent_so_far_sums_cost_over_finished_and_failed_runs(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    assert spent_so_far(_settings(sqlite_uri)) == 0.0
    bench = client.create_experiment("voice-arch/bench")
    conversations = client.create_experiment("voice-arch/conversations")

    _run(client, bench, 1.5)
    _run(client, conversations, 2.0, "FAILED")
    _run(client, bench, None)

    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(3.5)


def test_spent_so_far_ignores_other_experiments(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    _run(client, client.create_experiment("mini-rag"), 9.0)

    assert spent_so_far(_settings(sqlite_uri)) == 0.0


def test_spent_so_far_counts_the_latest_cost_metric_of_a_run(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    run = client.create_run(client.create_experiment("voice-arch/bench"), tags={"project": "voice-arch"})
    client.log_metric(run.info.run_id, "cost_usd", 1.0, 1000)
    client.log_metric(run.info.run_id, "cost_usd", 1.8, 2000)
    client.set_terminated(run.info.run_id)

    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(1.8)


def test_check_budget_stops_when_reaching_the_budget() -> None:
    with pytest.raises(BudgetExceeded) as err:
        check_budget(48.0, 2.0, 50.0)

    assert (err.value.spent, err.value.budget) == (48.0, 50.0)
    check_budget(47.9, 2.0, 50.0)


def test_spent_so_far_counts_soft_deleted_runs(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    bench = client.create_experiment("voice-arch/bench")
    _run(client, bench, 2.0)
    client.delete_run(_run(client, bench, 1.0))

    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(3.0)


def test_running_run_with_cost_counts_toward_budget(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    _run(client, client.create_experiment("voice-arch/conversations"), 3.0, status=None)

    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(3.0)


def test_crashed_run_without_cost_counts_at_the_estimate(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    bench = client.create_experiment("voice-arch/bench")
    conversations = client.create_experiment("voice-arch/conversations")
    _run(client, conversations, None, status=None)  # RUNNING, never logged a cost
    _run(client, bench, None, "FAILED")
    _run(client, bench, None, "FINISHED")  # finished without a cost: key unreadable (F-12), counts nothing

    expected = ESTIMATES_USD["conversations"] + ESTIMATES_USD["bench"]
    assert (ESTIMATES_USD["conversations"], ESTIMATES_USD["bench"]) == (15.0, 2.0)
    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(expected)


def test_run_with_cost_is_not_also_counted_at_the_estimate(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    _run(client, client.create_experiment("voice-arch/bench"), 0.4, "FAILED")

    assert spent_so_far(_settings(sqlite_uri)) == pytest.approx(0.4)
