"""Wire a new project into .pre-commit-config.yaml and ci.yml, and check that every project is wired.

The edits are text-level between `# >>> datalab-new: <label>` markers: a PyYAML dump would drop the comments.
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

import yaml

from datalab.project import ProjectError

PRE_COMMIT: Final = Path(".pre-commit-config.yaml")
CI: Final = Path(".github") / "workflows" / "ci.yml"
_BLOCK_ID: Final = re.compile(r"^ {6}- id: (\S+)$")
_MATRIX_ITEM: Final = re.compile(r"^ {10}- (\S+)$")


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


def _shape_error(what: str, detail: str) -> ProjectError:
    return ProjectError(f"wiring target has an unexpected shape: {what} {detail}")


def _at(value: object, *keys: str, what: str) -> object:
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise _shape_error(what, f"(missing {key!r})")
        # safe_load only yields str-keyed mappings here; isinstance cannot narrow dict[Unknown, Unknown]
        value = cast("dict[str, object]", value)[key]
    return value


def hook_ids(config: object) -> set[str]:
    what = ".pre-commit-config.yaml"
    repos = _at(config, "repos", what=what)
    if not isinstance(repos, list):
        raise _shape_error(what, "(repos is not a list)")
    ids: set[str] = set()
    for repo in cast("list[object]", repos):
        hooks = _at(repo, "hooks", what=what)
        if not isinstance(hooks, list):
            raise _shape_error(what, "(hooks is not a list)")
        for hook in cast("list[object]", hooks):
            hook_id = _at(hook, "id", what=what)
            if not isinstance(hook_id, str):
                raise _shape_error(what, "(hook id is not a string)")
            ids.add(hook_id)
    return ids


def matrix_entries(ci: object) -> list[str]:
    matrix = _at(ci, "jobs", "projects", "strategy", "matrix", "project", what="ci.yml")
    if not isinstance(matrix, list):
        raise _shape_error("ci.yml", f"matrix is {type(matrix).__name__}")
    items = cast("list[object]", matrix)
    if not all(isinstance(item, str) for item in items):
        raise _shape_error("ci.yml", "matrix has a non-string entry")
    return cast("list[str]", items)


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
    hooks = hook_ids(yaml.safe_load(pc_new))
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
