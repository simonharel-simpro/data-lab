"""Hook entry: map changed paths to project roots, run the vendored Hydra gate once per root (F-1)."""

import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
GATE: Final = REPO_ROOT / "tools" / "check_hydra_project.py"
GATE_TIMEOUT_S: Final = 120
_OC_ENV: Final = re.compile(r"\$\{\s*oc\.env\s*:")


def project_roots(paths: Sequence[str], repo_root: Path) -> list[Path]:
    projects = repo_root / "projects"
    if not paths:
        return sorted(p for p in projects.glob("*") if p.is_dir() and not p.name.startswith("."))
    found: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        absolute = path if path.is_absolute() else repo_root / path
        try:
            parts = absolute.relative_to(projects).parts
        except ValueError:
            continue
        if parts:
            found.add(projects / parts[0])
    return sorted(found)


def env_interpolations(project: Path) -> list[str]:
    configs = project / "configs"
    hits: list[str] = []
    for path in sorted(p for p in configs.rglob("*") if p.is_file() and p.suffix in {".yaml", ".yml"}):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _OC_ENV.search(line):
                hits.append(f"{path.relative_to(project)}:{number}")
    return hits


def _say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _run_gate(root: Path, rel: str) -> bool:
    try:
        done = subprocess.run(  # noqa: S603  # fixed argv: this interpreter + the vendored gate + a repo path, no shell
            [sys.executable, str(GATE), str(root)], check=False, timeout=GATE_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        _say(f"hydra-gate {rel}: timed out after {GATE_TIMEOUT_S} s")
        return False
    return done.returncode == 0


def _check(root: Path, repo_root: Path) -> bool:
    rel = root.relative_to(repo_root).as_posix()
    if not (root / "configs").is_dir():
        _say(f"skip {rel}: no configs/")
        return True
    _say(f"hydra-gate {rel}")
    ok = _run_gate(root, rel)
    for hit in env_interpolations(root):
        _say(f"{rel}/{hit}: ${{oc.env:}} interpolation is forbidden in configs")
        ok = False
    return ok


def main(argv: list[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    paths = sys.argv[1:] if argv is None else argv
    results = [_check(root, repo_root) for root in project_roots(paths, repo_root)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
