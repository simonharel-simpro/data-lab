"""MLflow preflight and a run that always carries the non-overridable tag `project=<name>`."""

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final

import httpx
import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from datalab.project import Project, experiment_name
from datalab.settings import Settings

logger = logging.getLogger(__name__)


_HTTP_DEFAULTS: Final = {"MLFLOW_HTTP_REQUEST_MAX_RETRIES": "2", "MLFLOW_HTTP_REQUEST_TIMEOUT": "30"}


class TrackingUnavailable(RuntimeError):
    pass


def _bound_http_retries() -> None:
    """MLflow's defaults (7 retries x 120 s, backoff 2) turn an outage into a ~20 min hang; a user value wins."""
    for key, value in _HTTP_DEFAULTS.items():
        os.environ.setdefault(key, value)


def preflight(uri: str) -> None:
    """Fail in seconds, not after hours of compute, when MLflow is unreachable."""
    _bound_http_retries()
    mlflow.set_tracking_uri(uri)
    logger.info("MLflow tracking URI: %s", mlflow.get_tracking_uri())
    if uri.startswith(("http://", "https://")):
        try:
            httpx.get(f"{uri.rstrip('/')}/health", timeout=5).raise_for_status()
        except httpx.HTTPError as err:
            raise TrackingUnavailable(f"MLflow not reachable at {uri}: {err}") from err
    try:
        MlflowClient(tracking_uri=uri).search_experiments(max_results=1)
    except MlflowException as err:
        raise TrackingUnavailable(f"MLflow at {uri} rejected a query: {err}") from err


@contextmanager
def tracked_run(
    project: Project,
    settings: Settings,
    run_name: str,
    sub: str | None = None,
    tags: Mapping[str, str] | None = None,
) -> Iterator[str]:
    """Open a run in `<name>` or `<name>/<sub>`; an exception inside marks it FAILED and is re-raised."""
    _bound_http_retries()
    extra = dict(tags or {})
    if "project" in extra:
        raise ValueError("tags may not override 'project': it always equals the project name")
    # Set explicitly, so a project that skips preflight never logs through an inherited MLFLOW_TRACKING_URI (F-5).
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name(project.name, sub))
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags({"project": project.name} | extra)
        yield run.info.run_id
