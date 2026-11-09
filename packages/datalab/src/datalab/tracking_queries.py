"""Read-side MLflow queries of a project's runs: spend, stale RUNNING runs, closing them. Re-exported by `tracking`."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from mlflow import MlflowClient
from mlflow.entities import Experiment, Run, RunStatus, ViewType
from mlflow.exceptions import MlflowException
from mlflow.store.entities.paged_list import PagedList

from datalab.project import experiment_name
from datalab.settings import Settings

_PAGE = 1000
_RUNNING: Final = RunStatus.to_string(RunStatus.RUNNING)


def _next_token[T](page: PagedList[T]) -> str | None:
    # mlflow leaves `PagedList.token` unannotated; it is a `str | None` page token.
    token: object = page.token  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]  # see above
    return token if isinstance(token, str) and token else None


def experiments_page(
    client: MlflowClient, *, max_results: int, filter_string: str | None = None, token: str | None = None
) -> tuple[list[Experiment], str | None]:
    """One page of experiments plus the next page token (None on the last page)."""
    # mlflow annotates `page_token` with an unresolved type, so the bound method is partially unknown.
    page = client.search_experiments(  # pyright: ignore[reportUnknownMemberType]  # see above
        view_type=ViewType.ALL, filter_string=filter_string, max_results=max_results, page_token=token
    )
    return list(page), _next_token(page)


@dataclass(frozen=True)
class StaleRun:
    run_id: str
    run_name: str
    experiment: str
    start_time: datetime


def _experiments(client: MlflowClient, project: str) -> dict[str, str]:
    """experiment id -> name for `<project>` and `<project>/*` (the app's rule); the name is NAME_RE-checked first."""
    name = experiment_name(project)
    found: dict[str, str] = {}
    token: str | None = None
    while True:
        page, token = experiments_page(client, filter_string=f"name LIKE '{name}%'", max_results=_PAGE, token=token)
        found |= {e.experiment_id: e.name for e in page if e.name == name or e.name.startswith(f"{name}/")}
        if token is None:
            return found


def _runs(client: MlflowClient, project: str, ids: list[str], extra: str = "") -> list[Run]:
    runs: list[Run] = []
    token: str | None = None
    while True:
        page = client.search_runs(
            ids,
            filter_string=f"tags.project = '{project}'{extra}",
            run_view_type=ViewType.ALL,
            max_results=_PAGE,
            page_token=token,
        )
        runs += list(page)
        token = _next_token(page)
        if token is None:
            return runs


def project_spend(project: str, settings: Settings) -> float:
    """Sum of `cost_usd` over every run of the project, whatever its status (RUNNING counts: F-7)."""
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    ids = list(_experiments(client, project))
    if not ids:
        return 0.0
    return sum(run.data.metrics.get("cost_usd", 0.0) for run in _runs(client, project, ids))


def stale_runs(
    project: str,
    settings: Settings,
    older_than: timedelta,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[StaleRun]:
    """RUNNING runs started before `now() - older_than`, by run id. Lists only: closing is `close_runs`."""
    if older_than <= timedelta(0):
        raise ValueError(f"older_than must be positive, got {older_than}")
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    experiments = _experiments(client, project)
    if not experiments:
        return []
    cutoff = now() - older_than
    running = _runs(client, project, list(experiments), f" and attributes.status = '{_RUNNING}'")
    stale = [
        StaleRun(
            run_id=run.info.run_id,
            run_name=run.info.run_name or "",
            experiment=experiments[run.info.experiment_id],
            start_time=datetime.fromtimestamp(run.info.start_time / 1000, UTC),
        )
        for run in running
    ]
    return sorted((s for s in stale if s.start_time < cutoff), key=lambda s: s.run_id)


def close_runs(project: str, settings: Settings, run_ids: Sequence[str]) -> list[str]:
    """Mark the named RUNNING runs of the project KILLED; all ids are checked before any is changed (F-9)."""
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    ids = sorted(set(run_ids))
    for run_id in ids:
        try:
            run = client.get_run(run_id)
        except MlflowException as err:
            raise ValueError(f"run {run_id} cannot be read: {err}") from err
        if run.info.status != _RUNNING or run.data.tags.get("project") != project:
            raise ValueError(f"run {run_id} is not a RUNNING run of project {project!r}")
    for run_id in ids:
        client.set_terminated(run_id, status="KILLED")
    return ids
