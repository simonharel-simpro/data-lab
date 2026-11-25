"""Fail if a Python module in packages|projects|templates/*/src/ or tools/ exceeds the line budget."""

import sys
from pathlib import Path

MAX_LINES = 200
WARN_LINES = 190
ROOTS = ("packages", "projects", "templates")
# Vendored / non-Python-tooling paths under tools/ (keep in sync with the file-size / check-function-length
# `exclude:` in .pre-commit-config.yaml).
_EXCLUDED_TOOLS = ("tools/check_hydra_project.py", "tools/pre_commit_checks/_layout.py")
_EXCLUDED_TOOLS_DIRS = ("tools/weavit-ui/",)


def _in_scope(path: Path) -> bool:
    parts = path.parts
    if path.suffix != ".py":
        return False
    if parts[:1] == ("tools",):
        posix = path.as_posix()
        return posix not in _EXCLUDED_TOOLS and not posix.startswith(_EXCLUDED_TOOLS_DIRS)
    return len(parts) >= 3 and parts[0] in ROOTS and parts[2] == "src"


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or [
        *(p for root in ROOTS for p in Path(root).glob("*/src/**/*.py")),
        *Path("tools").glob("**/*.py"),
    ]
    too_long: list[str] = []
    warnings: list[str] = []
    for path in paths:
        if not _in_scope(path):
            continue
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n > MAX_LINES:
            too_long.append(f"{path}: {n} lines > {MAX_LINES}")
        elif n >= WARN_LINES:
            warnings.append(f"warning: {path}: {n} lines (cap {MAX_LINES}): split before adding")
    for line in [*warnings, *too_long]:
        print(line, file=sys.stderr)
    return 1 if too_long else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
