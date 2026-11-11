"""`datalab-new <name> [--title T]`: copy templates/project to projects/<name>, atomically."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

from datalab import wiring
from datalab.project import ProjectError, is_datalab_checkout, package_name, validate_name, workspace_root
from datalab.resources import ruff_toml, template_dir

DATALAB_GIT_URL: Final = "https://github.com/simonharel-simpro/data-lab"
_PATH_SOURCE: Final = 'datalab = { path = "../../packages/datalab", editable = true }'
_GIT_SOURCE: Final = f'datalab = {{ git = "{DATALAB_GIT_URL}", subdirectory = "packages/datalab", branch = "main" }}'
_AUTH_FAILURE: Final = re.compile(
    r"could not read username|authentication failed|403|404|permission denied|repository not found", re.IGNORECASE
)
_IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".env", "uv.lock")
_PLACEHOLDER = "__DATALAB_"
_PACKAGE = "__DATALAB_PACKAGE__"


def _text_files(tree: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for path in sorted(tree.rglob("*")):
        if path.is_file() and not path.is_symlink():
            try:
                found.append((path, path.read_bytes().decode("utf-8")))
            except UnicodeDecodeError:
                continue  # binary file: copied as is
    return found


def _placeholders_left(tmp: Path) -> list[str]:
    in_text = [str(p.relative_to(tmp)) for p, text in _text_files(tmp) if _PLACEHOLDER in text]
    in_path = [str(p.relative_to(tmp)) for p in tmp.rglob("*") if _PLACEHOLDER in str(p.relative_to(tmp))]
    return sorted(set(in_text + in_path))


def _rename_package_paths(tmp: Path, pkg: str) -> None:
    named = [p for p in tmp.rglob("*") if _PACKAGE in p.name]
    for path in sorted(named, key=lambda p: len(p.parts), reverse=True):  # deepest first: parents keep their names
        path.rename(path.with_name(path.name.replace(_PACKAGE, pkg)))


def _rewrite(tmp: Path, name: str, title: str, pkg: str) -> None:
    for path, text in _text_files(tmp):
        # In the card the title is a JSON string, i.e. a YAML double-quoted scalar: `RAG: v2 # b` survives (G-7).
        shown = json.dumps(title, ensure_ascii=False) if path == tmp / "PROJECT.md" else title
        new = text.replace("__DATALAB_PROJECT__", name).replace("__DATALAB_TITLE__", shown).replace(_PACKAGE, pkg)
        if new != text:
            path.write_text(new, encoding="utf-8")
    _rename_package_paths(tmp, pkg)
    left = _placeholders_left(tmp)
    if left:
        raise ProjectError(f"unreplaced {_PLACEHOLDER}* placeholder in {left}")


def _uv_lock(project: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise ProjectError("uv not found on PATH; install uv to scaffold a locked project")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}  # a credential prompt would hang (F-1)
    try:
        done = subprocess.run(  # noqa: S603  # fixed argv from shutil.which, no shell, no user input
            [uv, "lock"],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired as err:
        raise ProjectError("uv lock timed out after 300 s") from err
    if done.returncode == 0:
        return
    detail = done.stderr.strip() or done.stdout.strip()
    if _AUTH_FAILURE.search(done.stderr):
        raise ProjectError(
            f"uv lock cannot fetch {DATALAB_GIT_URL}: you need read access and git credentials "
            f"(gh auth setup-git): {detail.splitlines()[-1]}"
        )
    raise ProjectError(f"uv lock failed (exit {done.returncode}): {detail}")


def _render_outside_source(project: Path) -> None:
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if _PATH_SOURCE not in text:
        raise ProjectError("template pyproject has no datalab source line")
    pyproject.write_text(text.replace(_PATH_SOURCE, _GIT_SOURCE), encoding="utf-8")


def _write_workspace_ruff(root: Path, text: str) -> bool:
    """Runs after the project is published: a failure here must not claim "nothing written"."""
    path = root / "ruff.toml"
    try:
        with open(path, "x", encoding="utf-8") as out:
            out.write(text)
    except FileExistsError:
        print(f"kept existing {path}")
    except OSError as err:
        print(f"datalab-new: project created but {path} not written: {err}", file=sys.stderr)
        return False
    return True


def _build(
    root: Path, tmp: Path, target: Path, names: tuple[str, str, str], lock: Callable[[Path], None]
) -> wiring.WiringPlan | None:
    name, title, pkg = names
    inside = is_datalab_checkout(root)
    shutil.copytree(template_dir(), tmp, ignore=_IGNORE)
    _rewrite(tmp, name, title, pkg)
    if not inside:
        _render_outside_source(tmp)
    lock(tmp)
    wiring_plan = wiring.plan(root, name) if inside else None  # outside: never read a foreign CI file (F-4)
    os.rename(tmp, target)
    return wiring_plan


def _wired(wiring_plan: wiring.WiringPlan, target: Path) -> bool:
    try:
        wiring.apply(wiring_plan)
    except OSError as err:
        print(
            f"created {target}, but hook/CI wiring failed: {err}; the parity test fails until it is fixed",
            file=sys.stderr,
        )
        return False
    return True


def _publish(root: Path, name: str, title: str, pkg: str, lock: Callable[[Path], None]) -> int:
    inside = is_datalab_checkout(root)
    if not inside:
        (root / "projects").mkdir(exist_ok=True)
    target = root / "projects" / name
    if target.exists() or target.is_symlink():
        print(f"datalab-new: {target} already exists; nothing written", file=sys.stderr)
        return 2
    tmp = root / "projects" / f".{name}.tmp-{secrets.token_hex(4)}"
    try:
        ruff_text = None if inside else ruff_toml().read_text(encoding="utf-8")  # resolved before anything is built
        wiring_plan = _build(root, tmp, target, (name, title, pkg), lock)
    except (OSError, ProjectError) as err:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"datalab-new: failed, nothing written: {err}", file=sys.stderr)
        return 1
    if ruff_text is not None and not _write_workspace_ruff(root, ruff_text):
        return 1
    if wiring_plan is not None and not _wired(wiring_plan, target):
        return 1
    print(f"created {target} (package {pkg}) in workspace {root}")
    print(f"next: cd projects/{name} && uv sync, then run /datalab:experiment")
    if not inside:
        print("no hook/CI wiring outside data-lab (#48)")
    return 0


def main(argv: list[str] | None = None, *, root: Path | None = None, lock: Callable[[Path], None] = _uv_lock) -> int:
    parser = argparse.ArgumentParser(prog="datalab-new", description="Create projects/<name> from the template.")
    parser.add_argument("name", help="project name: lowercase letters/digits, single dashes, not reserved")
    parser.add_argument("--title", help="card title (default: the name)")
    args = parser.parse_args(argv)
    try:
        name = validate_name(args.name)  # before any path is built: the path-traversal guard
        pkg = package_name(name)  # refused names write nothing (U-25)
        root = root or workspace_root()
    except ProjectError as err:
        print(f"datalab-new: {err}", file=sys.stderr)
        return 2
    return _publish(root, name, args.title or name, pkg, lock)
