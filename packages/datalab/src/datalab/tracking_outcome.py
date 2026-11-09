"""Per-parent-run tally of trial outcomes, tagged on the parent when it closes."""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

import mlflow
from mlflow.entities import RunStatus

from datalab.tags import Tag

logger = logging.getLogger(__name__)

_FAILED = RunStatus.to_string(RunStatus.FAILED)


@dataclass
class Outcome:
    children: int = 0
    failed: list[str] = field(default_factory=list[str])


# Outcomes of the trials of each open parent run, keyed by parent run id; popped by `tracked_run` when it closes.
OUTCOMES: dict[str, Outcome] = {}


def tag_outcome(parent_id: str) -> None:
    outcome = OUTCOMES.pop(parent_id, None)
    if outcome is None:
        return
    mlflow.set_tags(
        {
            Tag.N_CHILDREN.value: str(outcome.children),
            Tag.N_FAILED.value: str(len(outcome.failed)),
            Tag.FAILED_CANDIDATES.value: ",".join(sorted(outcome.failed)),
        }
    )


def after_failure(err: BaseException, what: str, cleanup: Callable[[], object]) -> None:
    """Run `cleanup` while `err` propagates; if it fails too, note that on `err` so the body's error stays raised."""
    try:
        cleanup()
    except Exception as cleanup_err:  # noqa: BLE001  # the body's error must win; this one is noted and logged
        err.add_note(f"{what} failed: {cleanup_err!r}")
        logger.warning("%s failed while handling %r: %r", what, err, cleanup_err)


@contextmanager
def ending_run() -> Generator[None, None, None]:
    """End the active run on exit: FAILED if the body raised, else FINISHED. Replaces `start_run`'s implicit exit.

    mlflow pops the run off its active-run stack before the store call, so a store outage never leaves it there.
    The run then stays RUNNING in the store; `stale_runs` / `close_runs` close it once MLflow is back.
    """
    try:
        yield
    except BaseException as err:
        after_failure(err, "ending the run as FAILED", lambda: mlflow.end_run(_FAILED))
        raise
    else:
        mlflow.end_run()
