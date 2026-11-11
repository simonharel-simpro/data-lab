"""Where the contracts, the project template and the ruff config live. Pure: stdlib only.

A checkout (editable install) reads the repo-root files; a wheel reads the copies hatch force-includes. The two
sources never back each other up: a missing file is an error, not a reason to read the other copy (F-7, U-5).
"""

import sys
from importlib.resources import files
from pathlib import Path

from datalab.project import ProjectError, repo_root


def _folder(packaged: str, checkout: str) -> Path:
    try:
        folder = repo_root() / checkout
    except ProjectError:
        folder = Path(str(files("datalab") / packaged))
    if not folder.is_dir():
        raise ProjectError(f"datalab resources: {folder} does not exist")
    return folder


def contract_path(name: str) -> Path:
    folder = _folder("contracts", "contracts")
    available = sorted(p.name for p in folder.iterdir() if p.is_file())
    if name not in available:  # also refuses `a/b` and `..`: only bare names of existing files pass
        raise ProjectError(f"unknown contract file {name!r} in {folder}: available {', '.join(available)}")
    return folder / name


def template_dir() -> Path:
    return _folder("template", "templates/project")


def ruff_toml() -> Path:
    try:
        path = repo_root() / "ruff.toml"
    except ProjectError:
        path = Path(str(files("datalab") / "ruff.toml"))
    if not path.is_file():
        raise ProjectError(f"datalab resources: {path} does not exist")
    return path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m datalab.resources <contracts file name>", file=sys.stderr)
        return 2
    try:
        print(contract_path(args[0]).resolve())
    except ProjectError as err:
        print(f"datalab.resources: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
