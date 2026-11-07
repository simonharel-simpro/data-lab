"""MLflow preflight, a run that always carries the non-overridable tag `project=<name>`, and its nested trials."""

import logging
import math
import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final

import httpx
import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from datalab.project import Project, experiment_name
from datalab.settings import Settings
from datalab.tags import Tag
from datalab.tracking_queries import StaleRun, close_runs, project_spend, stale_runs

__all__ = [
    "StaleRun", "TrackingUnavailable", "Trial", "TrialError", "close_runs", "preflight", "project_spend",
    "stale_runs", "tracked_run", "tracked_trial",
]  # fmt: skip

logger = logging.getLogger(__name__)


_HTTP_DEFAULTS: Final = {"MLFLOW_HTTP_REQUEST_MAX_RETRIES": "2", "MLFLOW_HTTP_REQUEST_TIMEOUT": "30"}


class TrackingUnavailable(RuntimeError):
    pass


class TrialError(RuntimeError):
    """A trial opened where the contract forbids it (no parent, nested, concurrent, parent without project tag)."""


@dataclass
class Trial:
    run_id: str
    candidate: str
    cost_usd: float = 0.0

    def add_cost(self, usd: float) -> None:
        """Logs the cumulative cost at once, so a crash later never hides money already spent (F-7)."""
        if not math.isfinite(usd) or usd < 0:
            raise ValueError(f"cost must be a finite, non-negative number, got {usd!r}")
        self.cost_usd += usd
        mlflow.log_metric("cost_usd", self.cost_usd)


@dataclass
class _Outcome:
    children: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class _Slot:
    lock: threading.Lock = field(default_factory=threading.Lock)
    open_trial: str | None = None


# Outcomes of the trials of each open parent run, keyed by parent run id; popped by `tracked_run` when it closes.
_OUTCOMES: dict[str, _Outcome] = {}
_SLOT: Final = _Slot()


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
        try:
            yield run.info.run_id
        finally:
            _tag_outcome(run.info.run_id)


def _tag_outcome(parent_id: str) -> None:
    outcome = _OUTCOMES.pop(parent_id, None)
    if outcome is None:
        return
    mlflow.set_tags(
        {
            Tag.N_CHILDREN.value: str(outcome.children),
            Tag.N_FAILED.value: str(len(outcome.failed)),
            Tag.FAILED_CANDIDATES.value: ",".join(sorted(outcome.failed)),
        }
    )


def _claim_slot(run_name: str) -> None:
    with _SLOT.lock:
        if _SLOT.open_trial is not None:
            raise TrialError(f"trial {_SLOT.open_trial!r} is still open: trials run one at a time (F-15)")
        _SLOT.open_trial = run_name


def _release_slot() -> None:
    with _SLOT.lock:
        _SLOT.open_trial = None


def _parent_of(parent_id: str) -> tuple[str, str]:
    """(its experiment id, its project) for the active parent run, or `TrialError`."""
    parent = MlflowClient().get_run(parent_id)
    project = parent.data.tags.get("project")
    if project is None:
        raise TrialError(f"the active run {parent.info.run_id} has no 'project' tag: open it with tracked_run")
    return parent.info.experiment_id, project


@contextmanager
def tracked_trial(
    run_name: str, tags: Mapping[str, str] | None = None, *, candidate: str | None = None
) -> Iterator[Trial]:
    """One child run of the open `tracked_run`, in the parent's experiment; it alone logs `cost_usd` (D-5)."""
    extra = dict(tags or {})
    if "project" in extra or Tag.CANDIDATE.value in extra:
        raise ValueError("tags may not override 'project' or 'candidate': pass candidate= instead")
    active = mlflow.active_run()
    if active is None:
        raise TrialError(f"trial {run_name!r} needs an open tracked_run as its parent")
    _claim_slot(run_name)
    parent_id, opened, failed = active.info.run_id, False, False
    try:
        experiment_id, project = _parent_of(parent_id)
        with mlflow.start_run(run_name=run_name, nested=True, experiment_id=experiment_id) as child:
            opened = True
            mlflow.set_tags({"project": project, Tag.CANDIDATE.value: candidate or run_name} | extra)
            trial = Trial(child.info.run_id, candidate or run_name)
            try:
                yield trial
            except BaseException:
                failed = True
                raise
            finally:
                mlflow.log_metric("cost_usd", trial.cost_usd)
    finally:
        _release_slot()
        if opened:
            outcome = _OUTCOMES.setdefault(parent_id, _Outcome())
            outcome.children += 1
            outcome.failed += [run_name] if failed else []
