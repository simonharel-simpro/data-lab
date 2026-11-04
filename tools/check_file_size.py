"""Fail if any Python module under packages/*/src/ or projects/*/src/ exceeds the line budget."""

import sys
from pathlib import Path

MAX_LINES = 200
ROOTS = ("packages", "projects")


def _in_scope(path: Path) -> bool:
    parts = path.parts
    return path.suffix == ".py" and len(parts) >= 3 and parts[0] in ROOTS and parts[2] == "src"


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or [p for root in ROOTS for p in Path(root).glob("*/src/**/*.py")]
    too_long = []
    for path in paths:
        if not _in_scope(path):
            continue
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n > MAX_LINES:
            too_long.append(f"{path}: {n} lines > {MAX_LINES}")
    for line in too_long:
        print(line, file=sys.stderr)
    return 1 if too_long else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
