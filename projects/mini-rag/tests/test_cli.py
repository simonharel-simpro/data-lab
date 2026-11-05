from pathlib import Path

import pytest
from pydantic import ValidationError

from datalab.project import Project
from mini_rag.index import Retrieval
from mini_rag.run import _args, main


def test_k_below_one_is_refused() -> None:
    with pytest.raises(SystemExit):
        _args(["--retrieval", "bm25", "--k", "0"])


def test_unknown_retrieval_is_refused() -> None:
    with pytest.raises(SystemExit):
        _args(["--retrieval", "bogus", "--k", "3"])


def test_missing_k_is_refused() -> None:
    with pytest.raises(SystemExit):
        _args(["--retrieval", "bm25"])


def test_valid_args_parse_with_n_unset() -> None:
    args = _args(["--retrieval", "bm25", "--k", "3"])

    assert args.retrieval is Retrieval.BM25
    assert args.k == 3
    assert args.n is None


def test_f_13_main_validates_config_before_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mini_rag.run.load", lambda: Project("mini-rag", tmp_path))
    monkeypatch.setattr("mini_rag.run.preflight", lambda *_: pytest.fail("I/O before config"))
    monkeypatch.setattr("mini_rag.run.connect_weaviate", lambda *_: pytest.fail("I/O before config"))

    with pytest.raises(ValidationError):
        main(["--retrieval", "bm25", "--k", "3"])
