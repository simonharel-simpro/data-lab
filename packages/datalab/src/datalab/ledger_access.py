"""The test partition's access rules and the append-only record of test looks. Pure."""

from datalab.ledger_model import AUDIT, LedgerError, RunLedger, Status, TestLook
from datalab.ledger_ops import dump, revalidate


def look_number(lg: RunLedger, split_sha: str) -> int:
    return 1 + sum(1 for look in lg.test_looks if look.split_sha256 == split_sha)


def test_access_problem(lg: RunLedger, split_sha: str, note: str | None) -> str | None:
    if lg.current_milestone != AUDIT:
        return f"the test partition is read at the audit; the current milestone is {lg.current_milestone}"
    if lg.milestones[AUDIT].status is Status.VALIDATED:
        return "the audit is already validated: the test partition is closed"
    if split_sha != lg.split_sha256:
        return (
            "split.json changed since the freeze: its hash differs from run.json split_sha256 "
            "(an edit, or git line-ending conversion: see .gitattributes)"
        )
    if look_number(lg, split_sha) > 1 and not (note or "").strip():
        return "a repeated test look on this split needs an expert note"
    return None


def test_access_allowed(lg: RunLedger, split_sha: str, note: str | None = None) -> bool:
    return test_access_problem(lg, split_sha, note) is None


def record_test_look(lg: RunLedger, split_sha: str, run_id: str, note: str | None) -> RunLedger:
    problem = test_access_problem(lg, split_sha, note)
    if problem is not None:
        raise LedgerError(problem)
    look = TestLook(split_sha256=split_sha, run_id=run_id, note=note or "").model_dump(mode="json")
    data = dump(lg)
    data["test_looks"].append(look)
    return revalidate(data)


# The names start with "test_" (the contract's wording): keep pytest from collecting them out of test modules.
test_access_problem.__test__ = False  # pyright: ignore[reportFunctionMemberAccess]  # stops pytest collecting it
test_access_allowed.__test__ = False  # pyright: ignore[reportFunctionMemberAccess]  # stops pytest collecting it
