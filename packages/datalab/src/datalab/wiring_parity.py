"""Check that every project folder is wired into .pre-commit-config.yaml and ci.yml."""

from pathlib import Path
from typing import Final

import yaml

from datalab.project import ProjectError
from datalab.wiring import CI, PRE_COMMIT, hook_ids, matrix_entries

_HYDRA_STEP: Final = "tools/pre_commit_checks/hydra_gate.py projects/${{ matrix.project }}"
_LEDGER_STEP: Final = "python -m datalab.ledger validate projects/${{ matrix.project }}"


def _project_names(root: Path) -> list[str]:
    folders = (root / "projects").glob("*")
    wired = (p for p in folders if p.is_dir() and not p.name.startswith(".") and (p / "pyproject.toml").is_file())
    return sorted(p.name for p in wired)


def _ci_problems(ci: object, names: list[str]) -> list[str]:
    job = ci.get("jobs", {}).get("projects") if isinstance(ci, dict) else None
    if not isinstance(job, dict):
        return ["ci.yml has no jobs.projects"]
    strategy = job.get("strategy") or {}
    try:
        matrix = matrix_entries(ci)
    except ProjectError as err:
        matrix = []
        problems = [str(err)]
    else:
        problems = []
    problems += [f"project {n} is missing from jobs.projects.strategy.matrix.project" for n in names if n not in matrix]
    problems += [f"matrix entry {m} has no projects/{m} directory" for m in matrix if m not in names]
    if strategy.get("fail-fast") is not False:
        problems.append("jobs.projects.strategy.fail-fast must be false")
    runs = [str(step.get("run", "")) for step in job.get("steps") or []]
    if not any(_HYDRA_STEP in run for run in runs):
        problems.append(f"jobs.projects has no step running {_HYDRA_STEP}")
    if not any(_LEDGER_STEP in run for run in runs):
        problems.append(f"jobs.projects has no step running {_LEDGER_STEP}")
    return problems


def parity_problems(root: Path) -> list[str]:
    names = _project_names(root)
    ids = hook_ids(yaml.safe_load((root / PRE_COMMIT).read_text(encoding="utf-8")))
    wanted = [f"{prefix}-{n}" for n in names for prefix in ("declared-deps", "gates")]
    problems = [f"missing hook {hook_id}" for hook_id in wanted if hook_id not in ids]
    ci = yaml.safe_load((root / CI).read_text(encoding="utf-8"))  # its `on:` key loads as True: never index "on"
    return problems + _ci_problems(ci, names)
