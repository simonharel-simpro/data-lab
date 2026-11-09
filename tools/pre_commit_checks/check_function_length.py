# recipe-version: 4
"""Pre-commit check: function and class size limits (functions <= 30 lines, classes <= 150 lines).

Adapted from recipes/linters/python-fastapi-layered/check_file_length.py (REVIEW 2026-11-08
migration M3.3). The file-length half of the recipe is dropped: `tools/check_file_size.py`
already gates files at 200 lines (with its 190-line warning band) over the same scope.

Scope: the files pre-commit passes, i.e. Python modules under `packages/*/src/`,
`projects/*/src/` and `templates/*/src/` (the hook's `files:` regex). Run with file
arguments; with none it falls back to the `[tool.layered-linters] src_roots` of the cwd.
The vendored `tools/pre_commit_checks/_layout.run_layer_check` (31 lines, FIX_PLAN D-9, #41)
is outside that scope by construction. Function/class limits have no grandfather ratchet:
they are local and cheap to fix.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, run_checker
from _layout import NO_SOURCE_ROOT_MSG, source_files

FUNCTION_LINE_LIMIT = 30
CLASS_LINE_LIMIT = 150


class SizeLimitChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.end_lineno is not None:
            span = node.end_lineno - node.lineno + 1
            if span > CLASS_LINE_LIMIT:
                self.violations.append(
                    Violation(
                        self.file_path,
                        node.lineno,
                        f"Class '{node.name}' is {span} lines (limit: {CLASS_LINE_LIMIT})",
                    )
                )
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.end_lineno is None:
            return
        span = node.end_lineno - node.lineno + 1
        if span > FUNCTION_LINE_LIMIT:
            self.violations.append(
                Violation(
                    self.file_path,
                    node.lineno,
                    f"Function '{node.name}' is {span} lines (limit: {FUNCTION_LINE_LIMIT})",
                )
            )


def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
    checker = SizeLimitChecker(file_path)
    checker.visit(tree)
    return checker.violations


def main() -> int:
    files = source_files()
    if files is None:
        print(NO_SOURCE_ROOT_MSG)
        return 1
    return run_checker(check_file, files, "Function/class size limits")


if __name__ == "__main__":
    sys.exit(main())
