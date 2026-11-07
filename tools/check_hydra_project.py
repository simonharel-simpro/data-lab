#!/usr/bin/env python3
# >>> vendored header
# Vendored verbatim from trouvetou assets/check_hydra_project.py on 2026-11-06,
# sha256 312f6242dc31e4d7930a13d33df9cbed3537aa2ff3fc444f0c9dcf67252a61b2. Do not edit: re-vendor, update the hash.
# <<< vendored header
"""Hydra-project gate — assert a generated run WIRES Hydra, not just looks Hydra-shaped.

A run can carry a full `configs/` tree and the ledger yet never import Hydra — loading YAML
by hand (`config.py` + `yaml.safe_load`), dispatching candidates by string name, and pinning
`hydra-core` in requirements without installing or using it. That is the ExpCelineOCR failure
(2026-07): Hydra's *shape* with none of its *wiring*, so `instantiate`, CLI overrides, and the
`--multirun` matrix are all silently absent.

This is the dedicated mechanical pass that catches that class before the modeling milestone
advances — a gate, not a reflex buried in a crowded prompt (Panoramix #39: a rule competing
for attention in a large prompt is unreliable; a single-purpose gate is deterministic).

Static file checks only: stdlib, no interpreter/venv import of the target, runs under any
`python3`. Exit 0 iff every check passes; non-zero (with a FAIL line per gap) otherwise.

Usage:  python check_hydra_project.py <run-or-project-dir>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# Vendored / generated / data dirs never hold the run's own source or config.
_SKIP_DIRS: Final[frozenset[str]] = frozenset({
    ".venv", "venv", ".git", "node_modules", "__pycache__", "mlruns",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "data"})

_IMPORT: Final[re.Pattern[str]] = re.compile(r"^\s*(import hydra|from hydra\b)", re.MULTILINE)
_MAIN: Final[re.Pattern[str]] = re.compile(r"@hydra\.main\b")
_INSTANTIATE: Final[re.Pattern[str]] = re.compile(r"\binstantiate\s*\(")
_DEFAULTS: Final[re.Pattern[str]] = re.compile(r"^\s*defaults\s*:", re.MULTILINE)
_TARGET: Final[re.Pattern[str]] = re.compile(r"^\s*_target_\s*:", re.MULTILINE)
_DECLARED: Final[re.Pattern[str]] = re.compile(r"hydra-core", re.IGNORECASE)


class CheckResult(NamedTuple):
    name: str
    passed: bool
    detail: str  # why it failed — shown only on FAIL


def _rel_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def _walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files under root with any of `suffixes`, skipping vendored/generated dirs."""
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in suffixes
        and not any(part in _SKIP_DIRS for part in _rel_parts(p, root))
    ]


def _read_all(paths: list[Path]) -> str:
    """Concatenate the readable text of `paths` (undecodable/unreadable files skipped)."""
    chunks: list[str] = []
    for path in paths:
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(chunks)


def _config_json(root: Path) -> list[Path]:
    """JSON files used as CONFIG (under a `configs/` dir) — the contract mandates YAML there."""
    return [p for p in _walk(root, (".json",)) if "configs" in _rel_parts(p, root)]


def _venv_hydra(root: Path) -> CheckResult | None:
    """If a local venv exists, verify hydra-core is actually installed (not just declared)."""
    site_dirs = [p for p in root.rglob("site-packages") if p.is_dir()]
    if not site_dirs:
        return None  # no local venv to inspect — the static code checks still stand
    installed = any((sp / "hydra").is_dir() for sp in site_dirs)
    return CheckResult(
        "hydra-core installed in the run venv", installed,
        "hydra-core declared but NOT installed (found omegaconf only?) — `import hydra` would fail")


def check_hydra_project(root: Path) -> list[CheckResult]:
    """Run every static Hydra-wiring check against `root` and return one result each."""
    py = _read_all(_walk(root, (".py",)))
    yaml = _read_all(_walk(root, (".yaml", ".yml")))
    deps = _read_all(_walk(root, (".toml", ".txt")))
    json_cfgs = _config_json(root)
    return [
        CheckResult("hydra imported (`import hydra` / `from hydra ...`)", bool(_IMPORT.search(py)),
                    "no `import hydra` in any .py — Hydra is not wired, config is hand-loaded"),
        CheckResult("entry point uses @hydra.main", bool(_MAIN.search(py)),
                    "no @hydra.main decorator — no Hydra composition / CLI overrides / multirun"),
        CheckResult("candidates built via instantiate + _target_",
                    bool(_INSTANTIATE.search(py)) and bool(_TARGET.search(yaml)),
                    "missing instantiate()/_target_ — candidates dispatched in code, not from config"),
        CheckResult("configs compose via a `defaults:` list", bool(_DEFAULTS.search(yaml)),
                    "no `defaults:` list — configs are plain data files, not composed groups"),
        CheckResult("configs are YAML, not JSON", not json_cfgs,
                    f"JSON used for config (contract mandates YAML): {[str(p) for p in json_cfgs]}"),
        CheckResult("hydra-core declared as a dependency", bool(_DECLARED.search(deps)),
                    "hydra-core absent from pyproject.toml / requirements*.txt"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert a generated run WIRES Hydra (not just its shape).")
    parser.add_argument("path", type=Path, help="run or project directory to check")
    root = parser.parse_args().path
    if not root.is_dir():
        print(f"[gate] not a directory: {root}", file=sys.stderr)
        return 2
    checks = check_hydra_project(root)
    venv = _venv_hydra(root)
    if venv is not None:
        checks.append(venv)
    failed = [c for c in checks if not c.passed]
    print(f"=== Hydra-project gate: {root} ===")
    for c in checks:
        print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}" + (f" — {c.detail}" if not c.passed else ""))
    if failed:
        print(f"\n❌ NOT a Hydra project — {len(failed)} check(s) failed. It carries Hydra's "
              "shape but doesn't wire the library (see CONTRACTS.md — adapt Hydra, don't drop it).")
        return 1
    print("\n✅ Hydra is wired: import + @hydra.main + instantiate/_target_ + defaults + declared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
