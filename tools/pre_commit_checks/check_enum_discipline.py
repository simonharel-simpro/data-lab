# recipe-version: 2
"""Pre-commit check: enum discipline — no raw string comparisons against known enum values.

`partition == "test"` should be `partition == Partition.TEST`. This check scans
`src/` of the tree it runs in (the hook's `--directory`) for a raw string literal
equal to a declared StrEnum value inside `==` / `!=` / `in` comparisons.
StrEnum class bodies are skipped (definitions).

The value map is per tree, because the trees reuse values with different
meanings (`correct` is `Decision.CORRECT` in datalab and `Outcome.CORRECT` in
mini-rag). A pilot also imports datalab, so its map is datalab's plus its own,
its own winning on a clash. Adapted from
recipes/linters/python-fastapi-layered/check_enum_discipline.py (FIX_PLAN
"Recurring Patterns" row: raw literal equal to a declared StrEnum value).
Update the maps when a StrEnum gains or loses a member.

Scope: comparisons only. A raw literal used as a dict key or a call argument
(e.g. an MLflow tag name) is not caught.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import Violation, run_checker
from _layout import NO_SOURCE_ROOT_MSG, source_files

_DATALAB: dict[str, str] = {
    # ledger_model.Status / Decision / Kind
    "todo": "Status.TODO",
    "produced": "Status.PRODUCED",
    "validated": "Status.VALIDATED",
    "validate": "Decision.VALIDATE",
    "correct": "Decision.CORRECT",
    "redo": "Decision.REDO",
    "training": "Kind.TRAINING",
    "comparison": "Kind.COMPARISON",
    "exploration": "Kind.EXPLORATION",
    # project.Goal
    "max": "Goal.MAX",
    "min": "Goal.MIN",
    # split.Partition / SplitStrategy
    "train": "Partition.TRAIN",
    "val": "Partition.VAL",
    "test": "Partition.TEST",
    "random": "SplitStrategy.RANDOM",
    "stratified": "SplitStrategy.STRATIFIED",
    "temporal": "SplitStrategy.TEMPORAL",
    "grouped": "SplitStrategy.GROUPED",
    # tags.Tag
    "candidate": "Tag.CANDIDATE",
    "split": "Tag.SPLIT",
    "entry": "Tag.ENTRY",
    "n_children": "Tag.N_CHILDREN",
    "n_failed": "Tag.N_FAILED",
    "failed_candidates": "Tag.FAILED_CANDIDATES",
    "test_look": "Tag.TEST_LOOK",
    "split_sha256": "Tag.SPLIT_SHA256",
    "data_sha256": "Tag.DATA_SHA256",
    "score_on": "Tag.SCORE_ON",
    "config_sha256": "Tag.CONFIG_SHA256",
    # wiring.Region
    "declared-deps": "Region.DECLARED_DEPS",
    "gates": "Region.GATES",
    "matrix": "Region.MATRIX",
}

_MINI_RAG: dict[str, str] = {
    # index.Retrieval
    "bm25": "Retrieval.BM25",
    "vector": "Retrieval.VECTOR",
    # scoring.Outcome
    "correct": "Outcome.CORRECT",
    "missing": "Outcome.MISSING",
    "hallucination": "Outcome.HALLUCINATION",
}

_VOICE_ARCH: dict[str, str] = {
    # arch.Arch
    "a": "Arch.A",
    "b": "Arch.B",
    "c": "Arch.C",
    # bench.Component
    "stt": "Component.STT",
    "tts": "Component.TTS",
    "llm": "Component.LLM",
    # booking.record.ProblemType
    "plumbing": "ProblemType.PLUMBING",
    "electrical": "ProblemType.ELECTRICAL",
    "hvac": "ProblemType.HVAC",
    "appliance": "ProblemType.APPLIANCE",
    "other": "ProblemType.OTHER",
    # call.Outcome
    "scored": "Outcome.SCORED",
    "timeout": "Outcome.TIMEOUT",
    "agent_lost": "Outcome.AGENT_LOST",
    "caller_fault": "Outcome.CALLER_FAULT",
    "provider_error": "Outcome.PROVIDER_ERROR",
    # personas.Behaviour
    "self_correction": "Behaviour.SELF_CORRECTION",
    "out_of_order": "Behaviour.OUT_OF_ORDER",
    "interrupter": "Behaviour.INTERRUPTER",
    "slot_change": "Behaviour.SLOT_CHANGE",
    "speller": "Behaviour.SPELLER",
    "vague_problem": "Behaviour.VAGUE_PROBLEM",
}

# Keyed by the package directory under the tree's src/.
KNOWN_ENUM_VALUES_BY_PACKAGE: dict[str, dict[str, str]] = {
    "datalab": _DATALAB,
    "mini_rag": {**_DATALAB, **_MINI_RAG},
    "voice_arch": {**_DATALAB, **_VOICE_ARCH},
}


# (file relative to the tree root, value) pairs that only look like an enum value.
ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/datalab/ledger.py", "validate"),  # the CLI subcommand, not Decision.VALIDATE
    }
)


def _is_dot_value_comparison(node: ast.Compare) -> bool:
    """ORM/serialization boundary often does `status_col.value == "active"` — allow it."""
    if isinstance(node.left, ast.Attribute) and node.left.attr == "value":
        return True
    return any(isinstance(c, ast.Attribute) and c.attr == "value" for c in node.comparators)


class EnumDisciplineChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path, known: dict[str, str]) -> None:
        self.file_path = file_path
        self.known = known
        self.violations: list[Violation] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_strenum = any(
            (isinstance(b, ast.Name) and b.id == "StrEnum") or (isinstance(b, ast.Attribute) and b.attr == "StrEnum")
            for b in node.bases
        )
        if is_strenum:
            return  # don't descend into enum class bodies
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if _is_dot_value_comparison(node):
            self.generic_visit(node)
            return
        operands: list[ast.expr] = [node.left, *node.comparators]
        for operand in operands:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                self._flag_if_known(operand.value, node.lineno)
        self.generic_visit(node)

    def _flag_if_known(self, value: str, lineno: int) -> None:
        suggestion = self.known.get(value)
        if suggestion is None or (self.file_path.as_posix(), value) in ALLOWED:
            return
        self.violations.append(
            Violation(
                self.file_path,
                lineno,
                f'Raw string "{value}" in comparison — use {suggestion} instead',
            )
        )


def _tree_package() -> str | None:
    """The single known package under ./src, or None (fail loud, never scan with an empty map)."""
    src = Path("src")
    if not src.is_dir():
        return None
    found = [p.name for p in src.iterdir() if p.is_dir() and p.name in KNOWN_ENUM_VALUES_BY_PACKAGE]
    return found[0] if len(found) == 1 else None


def main() -> int:
    package = _tree_package()
    if package is None:
        print(
            "FAIL: no known package under ./src — run from a tree root "
            f"(one of {sorted(KNOWN_ENUM_VALUES_BY_PACKAGE)}) or add the tree's map"
        )
        return 1
    known = KNOWN_ENUM_VALUES_BY_PACKAGE[package]
    files = source_files()
    if files is None:
        print(NO_SOURCE_ROOT_MSG)
        return 1

    def check_file(file_path: Path, tree: ast.AST) -> list[Violation]:
        checker = EnumDisciplineChecker(file_path, known)
        checker.visit(tree)
        return checker.violations

    return run_checker(check_file, files, f"Enum discipline in {package} (no raw string comparisons)")


if __name__ == "__main__":
    sys.exit(main())
