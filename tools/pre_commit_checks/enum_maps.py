"""This repo's per-tree StrEnum value maps for check_enum_discipline."""

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
