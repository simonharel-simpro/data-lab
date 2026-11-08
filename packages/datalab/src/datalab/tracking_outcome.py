"""Per-parent-run tally of trial outcomes, tagged on the parent when it closes."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import mlflow

from datalab.tags import Tag

logger = logging.getLogger(__name__)


@dataclass
class _Outcome:
    children: int = 0
    failed: list[str] = field(default_factory=list)


# Outcomes of the trials of each open parent run, keyed by parent run id; popped by `tracked_run` when it closes.
_OUTCOMES: dict[str, _Outcome] = {}


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


def _after_failure(err: BaseException, what: str, cleanup: Callable[[], None]) -> None:
    """Run `cleanup` while `err` propagates; if it fails too, note that on `err` so the body's error stays raised."""
    try:
        cleanup()
    except Exception as cleanup_err:  # the body's error must win; this one is noted and logged
        err.add_note(f"{what} failed: {cleanup_err!r}")
        logger.warning("%s failed while handling %r: %r", what, err, cleanup_err)
