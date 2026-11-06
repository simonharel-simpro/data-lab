from datetime import UTC, datetime

import pytest
from mlflow import MlflowClient

from voice_arch.budget import BudgetExceeded, check_budget, spent_so_far


def _run(client: MlflowClient, experiment_id: str, cost: float | None, status: str = "FINISHED") -> None:
    run = client.create_run(experiment_id)
    if cost is not None:
        client.log_metric(run.info.run_id, "cost_usd", cost, int(datetime.now(UTC).timestamp() * 1000))
    client.set_terminated(run.info.run_id, status=status)


def test_spent_so_far_sums_cost_over_finished_and_failed_runs(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    assert spent_so_far(client) == 0.0
    bench = client.create_experiment("voice-arch/bench")
    conversations = client.create_experiment("voice-arch/conversations")

    _run(client, bench, 1.5)
    _run(client, conversations, 2.0, "FAILED")
    _run(client, bench, None)

    assert spent_so_far(client) == pytest.approx(3.5)


def test_spent_so_far_ignores_other_experiments(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    _run(client, client.create_experiment("mini-rag"), 9.0)

    assert spent_so_far(client) == 0.0


def test_spent_so_far_counts_the_latest_cost_metric_of_a_run(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    run = client.create_run(client.create_experiment("voice-arch/bench"))
    client.log_metric(run.info.run_id, "cost_usd", 1.0, 1000)
    client.log_metric(run.info.run_id, "cost_usd", 1.8, 2000)
    client.set_terminated(run.info.run_id)

    assert spent_so_far(client) == pytest.approx(1.8)


def test_check_budget_stops_when_reaching_the_budget() -> None:
    with pytest.raises(BudgetExceeded) as err:
        check_budget(48.0, 2.0, 50.0)

    assert (err.value.spent, err.value.budget) == (48.0, 50.0)
    check_budget(47.9, 2.0, 50.0)


def test_spent_so_far_counts_soft_deleted_runs(sqlite_uri: str) -> None:
    client = MlflowClient(sqlite_uri)
    bench = client.create_experiment("voice-arch/bench")
    _run(client, bench, 2.0)
    deleted = client.create_run(bench)
    client.log_metric(deleted.info.run_id, "cost_usd", 1.0, 1000)
    client.set_terminated(deleted.info.run_id, status="FINISHED")
    client.delete_run(deleted.info.run_id)

    assert spent_so_far(client) == pytest.approx(3.0)
