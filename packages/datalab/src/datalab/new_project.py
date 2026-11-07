"""`datalab-new <name> [--title T]`: copy templates/project to projects/<name>, atomically."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from datalab import wiring
from datalab.project import ProjectError, repo_root, validate_name

_IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".env", "uv.lock")
_PLACEHOLDER = "__DATALAB_"


def _text_files(tree: Path) -> list[tuple[Path, str]]:
    found = []
    for path in sorted(tree.rglob("*")):
        if path.is_file() and not path.is_symlink():
            try:
                found.append((path, path.read_bytes().decode("utf-8")))
            except UnicodeDecodeError:
                continue  # binary file: copied as is
    return found


def _rewrite(tmp: Path, name: str, title: str) -> None:
    for path, text in _text_files(tmp):
        # In the card the title is a JSON string, i.e. a YAML double-quoted scalar: `RAG: v2 # b` survives (G-7).
        shown = json.dumps(title, ensure_ascii=False) if path == tmp / "PROJECT.md" else title
        new = text.replace("__DATALAB_PROJECT__", name).replace("__DATALAB_TITLE__", shown)
        if new != text:
            path.write_text(new, encoding="utf-8")
    left = [str(p.relative_to(tmp)) for p, text in _text_files(tmp) if _PLACEHOLDER in text]
    if left:
        raise ProjectError(f"unreplaced {_PLACEHOLDER}* placeholder in {left}")


def _uv_lock(project: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise ProjectError("uv not found on PATH; install uv to scaffold a locked project")
    try:
        done = subprocess.run(  # noqa: S603  # fixed argv from shutil.which, no shell, no user input
            [uv, "lock"], cwd=project, check=False, capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired as err:
        raise ProjectError("uv lock timed out after 300 s") from err
    if done.returncode != 0:
        raise ProjectError(f"uv lock failed (exit {done.returncode}): {done.stderr.strip() or done.stdout.strip()}")


def main(argv: list[str] | None = None, *, root: Path | None = None, lock: Callable[[Path], None] = _uv_lock) -> int:
    parser = argparse.ArgumentParser(prog="datalab-new", description="Create projects/<name> from the template.")
    parser.add_argument("name", help="project name: lowercase letters/digits, single dashes, not reserved")
    parser.add_argument("--title", help="card title (default: the name)")
    args = parser.parse_args(argv)
    try:
        name = validate_name(args.name)  # before any path is built: the path-traversal guard
        root = root or repo_root()
    except ProjectError as err:
        print(f"datalab-new: {err}", file=sys.stderr)
        return 2
    projects, template = root / "projects", root / "templates" / "project"
    target = projects / name
    if target.exists() or target.is_symlink():
        print(f"datalab-new: {target} already exists; nothing written", file=sys.stderr)
        return 2
    tmp = projects / f".{name}.tmp-{secrets.token_hex(4)}"
    try:
        shutil.copytree(template, tmp, ignore=_IGNORE)
        _rewrite(tmp, name, args.title or name)
        lock(tmp)
        wiring_plan = wiring.plan(root, name)
        os.rename(tmp, target)
    except (OSError, ProjectError) as err:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"datalab-new: failed, nothing written: {err}", file=sys.stderr)
        return 1
    try:
        wiring.apply(wiring_plan)
    except OSError as err:
        print(
            f"created {target}, but hook/CI wiring failed: {err}; the parity test fails until it is fixed",
            file=sys.stderr,
        )
        return 1
    print(f"created {target}\nnext: cd projects/{name} && uv sync")
    return 0
