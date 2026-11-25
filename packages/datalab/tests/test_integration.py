"""Live-stack checks (F-4) and the exact-name cleanup they rely on (F-3, S-11)."""

from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx
import pytest
from mlflow import MlflowClient

from datalab.project import Project, collection_name, experiment_name
from datalab.settings import Settings, connect_weaviate
from datalab.tracking import tracked_run


class _Collections(Protocol):
    def delete(self, name: str) -> None: ...


class _Experiments(Protocol):
    def get_experiment_by_name(self, name: str) -> object: ...

    def delete_experiment(self, experiment_id: str) -> None: ...


def cleanup(collections: _Collections, experiments: _Experiments, collection: str, experiment: str) -> None:
    """Delete exactly what the test created — never by prefix, so a real project is never touched."""
    collections.delete(collection)
    exp = experiments.get_experiment_by_name(experiment)
    if exp is not None:
        experiments.delete_experiment(exp.experiment_id)  # type: ignore[attr-defined]  # an mlflow Experiment


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg


def _require_stack(settings: Settings) -> None:
    probes = (
        f"http://{settings.weaviate_host}:{settings.weaviate_http_port}/v1/.well-known/ready",
        f"{settings.mlflow_tracking_uri.rstrip('/')}/health",
    )
    for url in probes:
        try:
            httpx.get(url, timeout=3).raise_for_status()
        except httpx.HTTPError as err:
            pytest.skip(f"data-lab stack down ({url}: {err}); run `docker compose up -d`")


class _FakeExperiment:
    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id


class _Recorder:
    def __init__(self, experiments: dict[str, str]) -> None:
        self.experiments = experiments
        self.deleted_collections: list[str] = []
        self.deleted_experiments: list[str] = []

    def delete(self, name: str) -> None:
        self.deleted_collections.append(name)

    def get_experiment_by_name(self, name: str) -> _FakeExperiment | None:
        return _FakeExperiment(self.experiments[name]) if name in self.experiments else None

    def delete_experiment(self, experiment_id: str) -> None:
        self.deleted_experiments.append(experiment_id)


def test_f_3_cleanup_deletes_only_created_names() -> None:
    fake = _Recorder({"datalab-test": "0", "datalab-test/tab": "1", "datalab-test/tab2": "2", "mini-rag": "3"})

    cleanup(fake, fake, "DatalabTest_tab_12345678", "datalab-test/tab")

    assert fake.deleted_collections == ["DatalabTest_tab_12345678"]
    assert fake.deleted_experiments == ["1"]


@pytest.mark.integration
def test_f_4_rest_insert_visible_via_grpc_query(tmp_path: Path) -> None:
    settings = _settings()
    _require_stack(settings)
    sub = "t" + uuid4().hex[:8]  # starts with a letter, so NAME_RE accepts it (G-4)
    name = collection_name("datalab-test", sub)  # datalab-test is reserved: no real project can own it
    experiment = experiment_name("datalab-test", sub)
    mlflow_client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    with connect_weaviate(settings) as client:
        try:
            collection = client.collections.create(name)
            collection.data.insert({"text": "split brain detector"})  # REST
            hits = collection.query.bm25(query="detector", limit=5)  # gRPC
            assert len(hits.objects) == 1

            with tracked_run(Project(name="datalab-test", root=tmp_path), settings, "it", sub=sub) as run_id:
                pass
            run = mlflow_client.get_run(run_id)
            assert run.data.tags["project"] == "datalab-test"
            assert mlflow_client.get_experiment(run.info.experiment_id).name == experiment
        finally:
            cleanup(client.collections, mlflow_client, name, experiment)
    assert mlflow_client.get_experiment_by_name(experiment) is None or (
        # None-checked just above.
        mlflow_client.get_experiment_by_name(experiment).lifecycle_stage == "deleted"  # type: ignore[union-attr]  # get_experiment_by_name returns Optional; the experiment was created above
    )
