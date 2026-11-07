"""Wire a new project into .pre-commit-config.yaml and ci.yml, and check that every project is wired.

The edits are text-level between `# >>> datalab-new: <label>` markers: a PyYAML dump would drop the comments.
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import yaml

from datalab.project import ProjectError

PRE_COMMIT: Final = Path(".pre-commit-config.yaml")
CI: Final = Path(".github") / "workflows" / "ci.yml"
_BLOCK_ID: Final = re.compile(r"^ {6}- id: (\S+)$")
_MATRIX_ITEM: Final = re.compile(r"^ {10}- (\S+)$")
_HYDRA_STEP: Final = "tools/pre_commit_checks/hydra_gate.py projects/${{ matrix.project }}"
_LEDGER_STEP: Final = "python -m datalab.ledger validate projects/${{ matrix.project }}"


class Region(StrEnum):
    DECLARED_DEPS = "declared-deps"
    GATES = "gates"
    MATRIX = "matrix"


@dataclass(frozen=True)
class WiringPlan:
    writes: tuple[tuple[Path, str], ...]


def declared_deps_block(name: str) -> str:
    return (
        f"      - id: declared-deps-{name}\n"
        f"        name: {name} imports are declared dependencies\n"
        f"        entry: uv run --locked --directory projects/{name} python"
        " ../../tools/pre_commit_checks/check_declared_dependencies.py\n"
        "        language: system\n"
        "        pass_filenames: false\n"
        f"        files: ^(projects/{name}/|tools/pre_commit_checks/)\n"
    )


def gates_block(name: str) -> str:
    return (
        f"      - id: gates-{name}\n"
        f"        name: {name} gates (contracts, types) + unit tests + coverage floor\n"
        f"        entry: bash -c 'cd projects/{name} && uv run --locked lint-imports && uv run --locked pyright"
        " && uv run --locked pytest -q --cov'\n"
        "        language: system\n"
        "        pass_filenames: false\n"
        "        stages: [pre-push]\n"
        f"        files: ^(projects/{name}/|packages/datalab/src/)\n"
    )


def _region(text: str, label: Region) -> tuple[int, int]:
    """Offsets of the body between the open and close marker lines; each marker must occur exactly once."""
    opens = list(re.finditer(rf"^ *# >>> datalab-new: {re.escape(label)}\n", text, re.MULTILINE))
    closes = list(re.finditer(rf"^ *# <<< datalab-new: {re.escape(label)}$", text, re.MULTILINE))
    if len(opens) != 1 or len(closes) != 1 or closes[0].start() < opens[0].end():
        raise ProjectError(f"expected exactly one '# >>> / # <<< datalab-new: {label}' marker pair")
    return opens[0].end(), closes[0].start()


def _splice(text: str, label: Region, merge: Callable[[str], str]) -> str:
    start, end = _region(text, label)
    return text[:start] + merge(text[start:end]) + text[end:]


def _merge_blocks(body: str, block: str) -> str:
    blocks: dict[str, str] = {}
    current: str | None = None
    for line in body.splitlines(keepends=True):
        found = _BLOCK_ID.match(line.rstrip("\n"))
        if found:
            current = found.group(1)
            if current in blocks:
                raise ProjectError(f"duplicate hook id {current!r} in a datalab-new region")
            blocks[current] = ""
        elif current is None:
            raise ProjectError(f"unexpected text before the first hook in a datalab-new region: {line.strip()!r}")
        blocks[current] += line
    new_id = _BLOCK_ID.match(block.splitlines()[0])
    if new_id is None:  # pragma: no cover  # blocks come from this module
        raise ProjectError("malformed generated block")
    blocks.setdefault(new_id.group(1), block)
    return "".join(blocks[key] for key in sorted(blocks))


def _merge_matrix(body: str, name: str) -> str:
    items = {name}
    for line in body.splitlines():
        found = _MATRIX_ITEM.match(line)
        if found is None:
            raise ProjectError(f"unexpected line in the datalab-new matrix region: {line!r}")
        items.add(found.group(1))
    return "".join(f"          - {item}\n" for item in sorted(items))


def _checked(text: str, path: Path) -> None:
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ProjectError(f"{path}: wiring would produce invalid YAML: {err}") from err


def _hook_ids(config: object) -> set[str]:
    try:
        return {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}  # pyright: ignore[reportIndexIssue]
    except (KeyError, TypeError, AttributeError) as err:
        raise ProjectError(f"wiring target has an unexpected shape: .pre-commit-config.yaml {err!r}") from err


def matrix_entries(ci: object) -> list[object]:
    try:
        matrix = ci["jobs"]["projects"]["strategy"]["matrix"]["project"]  # pyright: ignore[reportIndexIssue]
    except (KeyError, TypeError, AttributeError) as err:
        raise ProjectError(f"wiring target has an unexpected shape: ci.yml {err!r}") from err
    if not isinstance(matrix, list):
        raise ProjectError(f"wiring target has an unexpected shape: ci.yml matrix is {type(matrix).__name__}")
    return matrix  # pyright: ignore[reportUnknownVariableType]


def plan(root: Path, name: str) -> WiringPlan:
    pc_path, ci_path = root / PRE_COMMIT, root / CI
    try:
        pc_old = pc_path.read_text(encoding="utf-8")
        ci_old = ci_path.read_text(encoding="utf-8")
    except OSError as err:
        raise ProjectError(f"cannot read wiring target: {err}") from err
    pc_new = _splice(pc_old, Region.DECLARED_DEPS, lambda body: _merge_blocks(body, declared_deps_block(name)))
    pc_new = _splice(pc_new, Region.GATES, lambda body: _merge_blocks(body, gates_block(name)))
    ci_new = _splice(ci_old, Region.MATRIX, lambda body: _merge_matrix(body, name))
    for path, text in ((pc_path, pc_new), (ci_path, ci_new)):
        _checked(text, path)
    hooks = _hook_ids(yaml.safe_load(pc_new))
    matrix = matrix_entries(yaml.safe_load(ci_new))
    if not {f"declared-deps-{name}", f"gates-{name}"} <= hooks or name not in matrix:
        raise ProjectError(f"wiring for {name} did not land in the hook ids or the CI matrix")
    changed = tuple((p, new) for p, old, new in ((pc_path, pc_old, pc_new), (ci_path, ci_old, ci_new)) if new != old)
    return WiringPlan(writes=changed)


def apply(wiring_plan: WiringPlan) -> None:
    for path, text in wiring_plan.writes:
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def _project_names(root: Path) -> list[str]:
    folders = (root / "projects").glob("*")
    wired = (p for p in folders if p.is_dir() and not p.name.startswith(".") and (p / "pyproject.toml").is_file())
    return sorted(p.name for p in wired)


def _ci_problems(ci: object, names: list[str]) -> list[str]:
    job = ci.get("jobs", {}).get("projects") if isinstance(ci, dict) else None
    if not isinstance(job, dict):
        return ["ci.yml has no jobs.projects"]
    strategy = job.get("strategy") or {}
    matrix = (strategy.get("matrix") or {}).get("project") or []
    problems = [f"project {n} is missing from jobs.projects.strategy.matrix.project" for n in names if n not in matrix]
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
    pre_commit = yaml.safe_load((root / PRE_COMMIT).read_text(encoding="utf-8"))
    ids = {hook["id"] for repo in pre_commit["repos"] for hook in repo["hooks"]}
    wanted = [f"{prefix}-{n}" for n in names for prefix in ("declared-deps", "gates")]
    problems = [f"missing hook {hook_id}" for hook_id in wanted if hook_id not in ids]
    ci = yaml.safe_load((root / CI).read_text(encoding="utf-8"))  # its `on:` key loads as True: never index "on"
    return problems + _ci_problems(ci, names)
