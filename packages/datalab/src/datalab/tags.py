"""MLflow tag names; the single source is contracts/mlflow_tags.json (compared by tests on both sides)."""

from enum import StrEnum


class Tag(StrEnum):
    CANDIDATE = "candidate"
    SPLIT = "split"
    ENTRY = "entry"
    N_CHILDREN = "n_children"
    N_FAILED = "n_failed"
    FAILED_CANDIDATES = "failed_candidates"
    TEST_LOOK = "test_look"
    SPLIT_SHA256 = "split_sha256"
    DATA_SHA256 = "data_sha256"
    SCORE_ON = "score_on"
    CONFIG_SHA256 = "config_sha256"
