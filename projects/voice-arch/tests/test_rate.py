from pathlib import Path

import pytest
from mlflow import MlflowClient

from datalab.project import Project
from datalab.settings import Settings
from voice_arch.rate import log_rating


def _dl(uri: str) -> Settings:
    return Settings(mlflow_tracking_uri=uri)


def test_u_6_rating_run_never_logs_exact_rate(sqlite_uri: str, tmp_path: Path) -> None:
    project = Project(name="voice-arch", root=tmp_path)
    rating = 4

    log_rating(project, _dl(sqlite_uri), "b", rating, "sounded natural")

    client = MlflowClient(sqlite_uri)
    experiment = client.get_experiment_by_name("voice-arch/human")
    assert experiment is not None
    (run,) = client.search_runs([experiment.experiment_id])
    assert run.data.metrics == {"human_rating": float(rating)}
    assert run.data.tags["source"] == "human"
    assert run.data.tags["arch"] == "b"
    assert run.data.tags["notes"] == "sounded natural"
    assert run.info.run_name == "human-b"


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_rating_out_of_range_refused(sqlite_uri: str, tmp_path: Path, rating: int) -> None:
    project = Project(name="voice-arch", root=tmp_path)

    with pytest.raises(ValueError, match="between 1 and 5"):
        log_rating(project, _dl(sqlite_uri), "a", rating, None)

    assert MlflowClient(sqlite_uri).get_experiment_by_name("voice-arch/human") is None
