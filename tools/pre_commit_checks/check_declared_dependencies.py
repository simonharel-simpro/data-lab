# recipe-version: 1
"""Pre-commit check: every third-party import is a declared dependency.

An `import foo` where `foo` is neither stdlib, nor first-party, nor provided by a
package in `[project.dependencies]` / `[project.optional-dependencies]` /
`[dependency-groups]` / the lockfile is a **production-down bug waiting to
happen**: it works in a dev env where the package is incidentally installed,
then `uv sync --frozen` (Docker/CI) cannot install it and the app won't import.

Real case: `app/routers/org_reports.py` imported `reportlab`, declared nowhere —
the frozen image couldn't start and the whole test suite failed at conftest
import. A cheap AST-vs-manifest check catches it instantly.

Import->distribution mapping (PIL->pillow, yaml->PyYAML) is resolved via
`importlib.metadata.packages_distributions()` against the RUNNING env, so under
`uv run` (pre-commit/CI) it is authoritative; a normalized-name match is the
fallback. Lockfile names are accepted, so the check flags the genuinely-absent,
not the merely-transitive.
"""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, emit_result, parse_file
from _layout import NO_SOURCE_ROOT_MSG, module_for_path, source_files

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]

try:
    from importlib.metadata import packages_distributions
except ImportError:  # pragma: no cover - Python < 3.10
    # Without it, dist->import aliases (pillow->PIL) are unknown and every aliased
    # import would be reported undeclared. Skipping is correct; guessing is not.
    packages_distributions = None  # type: ignore[assignment]

_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def _normalize(name: str) -> str:
    """PEP 503-ish: lowercase and unify -_. so import/dist names compare equal."""
    out = name.strip().lower()
    for ch in "-_.":
        out = out.replace(ch, "-")
    return out


def _dep_name(spec: str) -> str:
    """Distribution name from a requirement spec ('fastapi[std]>=1' -> 'fastapi')."""
    match = _NAME_RE.match(spec.strip())
    return match.group(0) if match else ""


def _declared_dists(pyproject: Path, lock: Path) -> set[str]:
    """Normalised dist names from pyproject deps (+ optional + groups) and the lock."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8")) if tomllib else {}
    project = data.get("project", {})
    specs: list[str] = list(project.get("dependencies", []) or [])
    for group in (project.get("optional-dependencies", {}) or {}).values():
        specs += list(group)
    for group in (data.get("dependency-groups", {}) or {}).values():
        specs += [g for g in group if isinstance(g, str)]
    names = [_dep_name(s) for s in specs]
    if tomllib is not None and lock.exists():
        lock_data = tomllib.loads(lock.read_text(encoding="utf-8"))
        names += [p.get("name", "") for p in lock_data.get("package", []) if isinstance(p, dict)]
    return {_normalize(n) for n in names if n}


def _first_party_tops(files: list[Path]) -> set[str]:
    """Normalised top-level names under the source roots (root prefix already stripped)."""
    return {_normalize(module_for_path(f).split(".", 1)[0]) for f in files if module_for_path(f)}


def _provided_import_names(declared: set[str]) -> set[str]:
    """Import names the installed env maps to a declared distribution (PIL->pillow…)."""
    if packages_distributions is None:
        return set()
    return {
        import_name
        for import_name, dists in packages_distributions().items()
        if any(_normalize(d) in declared for d in dists)
    }


def _imported_tops(tree: ast.AST) -> set[tuple[str, int]]:
    """(top-level module, lineno) for every absolute import in the tree."""
    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add((node.module.split(".")[0], node.lineno))
    return found


def _find_undeclared(files: list[Path], allowed: set[str], provided: set[str]) -> list[Violation]:
    stdlib = sys.stdlib_module_names
    violations: list[Violation] = []
    seen: set[str] = set()
    for file_path in files:
        tree = parse_file(file_path)
        if tree is None:
            continue
        for top, lineno in sorted(_imported_tops(tree), key=lambda p: p[1]):
            if top in stdlib or top in provided or _normalize(top) in allowed or top in seen:
                continue
            seen.add(top)
            violations.append(
                Violation(file_path, lineno, f"import '{top}' is not a declared dependency — add it to pyproject.toml")
            )
    return violations


def main() -> int:
    files = source_files()
    if files is None:
        print(NO_SOURCE_ROOT_MSG)
        return 1
    pyproject = Path("pyproject.toml")
    if tomllib is None or packages_distributions is None or not pyproject.exists():
        print("no pyproject.toml / tomllib / packages_distributions — skipping declared-dependency check")
        emit_result("SKIP", 0, 0)
        return 0
    declared = _declared_dists(pyproject, Path("uv.lock"))
    allowed = declared | _first_party_tops(files)
    violations = _find_undeclared(files, allowed, _provided_import_names(declared))
    if violations:
        print("=" * 70)
        print("VIOLATION: Undeclared third-party dependencies")
        print("=" * 70)
        for v in violations:
            print(f"  {v}")
        print(f"\nTotal: {len(violations)} undeclared import(s)")
        emit_result("FAIL", len(files), len(violations))
        return 1
    print(f"OK: all third-party imports are declared — checked {len(files)} file(s)")
    emit_result("PASS", len(files), 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
