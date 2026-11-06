"""Reads the sweeps back from MLflow: the cost of the last full sweep, and the inputs of `decide`."""

from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.project import experiment_name
from voice_arch.arch import Arch

_FULL_FINISHED = "tags.full = 'true' and attributes.status = 'FINISHED'"


def _latest(client: MlflowClient, sub: str, filter_string: str) -> Run | None:
    experiment = client.get_experiment_by_name(experiment_name("voice-arch", sub))
    if experiment is None:
        return None
    runs = client.search_runs(
        [experiment.experiment_id], filter_string=filter_string, order_by=["attributes.start_time DESC"], max_results=1
    )
    return runs[0] if runs else None


def last_full_sweep_cost(client: MlflowClient) -> float | None:
    """`cost_usd` of the newest FINISHED full sweep of any arch (the budget estimate for the next one, F-4b)."""
    run = _latest(client, "conversations", _FULL_FINISHED)
    return None if run is None else run.data.metrics.get("cost_usd")


def human_ratings(client: MlflowClient, arch: Arch) -> list[int]:
    experiment = client.get_experiment_by_name(experiment_name("voice-arch", "human"))
    if experiment is None:
        return []
    runs = client.search_runs([experiment.experiment_id], filter_string=f"tags.arch = '{arch.value}'", max_results=1000)
    return [round(r.data.metrics["human_rating"]) for r in runs if "human_rating" in r.data.metrics]


def latest_full_metrics(client: MlflowClient) -> dict[Arch, dict[str, float]]:
    """The metrics of the newest FINISHED full sweep of each arch that has one."""
    found: dict[Arch, dict[str, float]] = {}
    for arch in Arch:
        run = _latest(client, "conversations", f"{_FULL_FINISHED} and tags.arch = '{arch.value}'")
        if run is not None:
            found[arch] = dict(run.data.metrics)
    return found
