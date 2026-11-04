"""Layout discovery for the layered-architecture checks.

ONE place that knows how a project is laid out, so no individual check hardcodes
`src/<package>/<layer>` — the F-67 silent-skip failure mode where a check
returns green simply because it couldn't find the layer it was meant to scan.

Layout is AUTO-DETECTED by default (any `routers/`/`routes/`, `services/`, …
package under the source roots) and can be pinned or extended via a
`[tool.layered-linters]` table in the project's pyproject.toml:

    [tool.layered-linters]
    src_roots = ["src"]                     # where to look for layers
    required_layers = ["routers", "services"]  # missing one of these -> FAIL
    [tool.layered-linters.layer_dirs]
    routers = ["routers", "routes", "api"]  # extra dir names for a layer

`required_layers` is the fail-loud opt-in: a declared layer that resolves to no
directory fails the check instead of skipping. Without it, auto-detection is
robust enough that "found nothing" means "genuinely absent" (safe to skip).
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

from _base import Violation, emit_result, iter_python_files, run_checker

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

_DEFAULT_SRC_ROOTS: tuple[str, ...] = ("src",)
_DEFAULT_LAYER_DIRS: dict[str, tuple[str, ...]] = {
    "routers": ("routers", "routes", "api"),
    "services": ("services",),
    "workflows": ("workflows",),
    "repositories": ("repositories", "repos"),
    "models": ("models",),
    "enums": ("enums",),
}


@cache
def _config() -> dict[str, object]:
    pyproject = Path("pyproject.toml")
    if tomllib is None or not pyproject.exists():
        return {}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    tool = data.get("tool", {})
    return tool.get("layered-linters", {}) if isinstance(tool, dict) else {}


def source_roots() -> tuple[Path, ...]:
    """Existing source roots — config `src_roots` or the `src/` default."""
    configured = _config().get("src_roots", _DEFAULT_SRC_ROOTS)
    return tuple(Path(str(r)) for r in configured if Path(str(r)).exists())  # type: ignore[union-attr]


NO_SOURCE_ROOT_MSG = (
    "no source root found — set [tool.layered-linters] src_roots in your "
    "pyproject.toml (it defaults to ['src']); nothing scanned"
)


def source_files(*, extra_dirs: tuple[str, ...] = ()) -> list[Path] | None:
    """Python files to check: the filenames a runner passed on argv, else a
    full scan of the configured source roots (+ any `extra_dirs` like 'tests').

    Honouring argv is what lets pre-commit check exactly the STAGED files;
    honouring `source_roots()` is what lets a non-`src/` layout be scanned at
    all. Returns None only when there is genuinely nothing to scan — no argv
    AND no configured source root exists — so the caller prints
    NO_SOURCE_ROOT_MSG and exits 1 (loud, never a silent pass).
    """
    cli = [Path(a) for a in sys.argv[1:]]
    if cli:
        return [f for f in cli if f.suffix == ".py" and f.exists()]
    roots = source_roots()
    extras = tuple(d for d in (Path(x) for x in extra_dirs) if d.exists())
    if not roots and not extras:
        return None
    files: list[Path] = [f for root in roots for f in iter_python_files(root)]
    for extra in extras:
        files.extend(iter_python_files(extra, exclude_patterns=["__pycache__", ".venv"]))
    return files


def required_layers() -> frozenset[str]:
    declared = _config().get("required_layers", ())
    return frozenset(str(layer) for layer in declared)  # type: ignore[union-attr]


def _layer_dir_names(layer: str) -> tuple[str, ...]:
    overrides = _config().get("layer_dirs", {})
    if isinstance(overrides, dict) and layer in overrides:
        return tuple(str(n) for n in overrides[layer])
    return _DEFAULT_LAYER_DIRS.get(layer, (layer,))


def discover_layer_dirs(layer: str) -> tuple[Path, ...]:
    """Every directory under the source roots whose name matches `layer`."""
    names = _layer_dir_names(layer)
    found: set[Path] = set()
    for root in source_roots():
        found.update(p for p in root.rglob("*") if p.is_dir() and p.name in names)
    return tuple(sorted(found))


def module_for_path(path: Path) -> str:
    """Dotted import path for a file/dir, with the source root stripped.

    `src/agents/dispatch/models/route.py` -> `agents.dispatch.models.route`.
    Stripping the source root is what makes import matching work regardless of
    package name (and fixes the F-67 `src.`-prefix derivation bug).
    """
    parts = path.with_suffix("").parts
    for root in source_roots():
        root_parts = root.parts
        if parts[: len(root_parts)] == root_parts:
            return ".".join(parts[len(root_parts) :])
    return ".".join(parts)


def layer_module_prefixes(layer: str) -> frozenset[str]:
    """Dotted package prefixes for a layer, e.g. {'agents.dispatch.models'}."""
    return frozenset(module_for_path(d) for d in discover_layer_dirs(layer))


def module_matches(name: str, prefixes: frozenset[str]) -> str | None:
    """Return the matched prefix if `name` is, or is under, one of `prefixes`."""
    for prefix in prefixes:
        if prefix and (name == prefix or name.startswith(prefix + ".")):
            return prefix
    return None


def run_layer_check(
    layer: str,
    check_file: Callable[[Path, ast.AST], list[Violation]],
    description: str,
    *,
    exclude_init: bool = False,
) -> int:
    """Discover `layer`, scan its files, report — failing loud if required."""
    dirs = discover_layer_dirs(layer)
    if not dirs:
        roots = [str(r) for r in source_roots()] or ["(no source root found)"]
        if layer in required_layers():
            print(
                f"FAIL: required layer '{layer}' not found under {roots} "
                f"(looked for dir names {_layer_dir_names(layer)})"
            )
            emit_result("FAIL", 0, 0)
            return 1
        print(
            f"No '{layer}' layer found under {roots} — skipping "
            "(add it to [tool.layered-linters].required_layers to fail loudly)"
        )
        emit_result("SKIP", 0, 0)
        return 0

    files: list[Path] = []
    for directory in dirs:
        files.extend(iter_python_files(directory))
    if exclude_init:
        files = [f for f in files if f.name != "__init__.py"]
    return run_checker(check_file, files, description)
