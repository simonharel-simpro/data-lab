import json
from pathlib import Path

import pytest
from mlflow import MlflowClient
from mlflow.entities import Run
from mlflow.exceptions import MlflowException

from datalab.project import Project
from datalab.settings import Settings
from mini_rag.corpus import Chunk
from mini_rag.generate import GenerationError
from mini_rag.index import Retrieval
from mini_rag.questions import Question
from mini_rag.run import Answer, RunConfig, run
from mini_rag.settings import PilotSettings

_QUESTIONS = [
    Question(id="q1", question="Which port does MLflow use?", answer="5050"),
    Question(id="q2", question="Which Weaviate REST port?", answer="8090"),
    Question(id="q3", question="Which gRPC port?", answer="50052"),
    Question(id="q4", question="Admin password?", answer=None),
]
_ANSWERS = {"q1": "5050", "q2": "It is 8090.", "q3": "I don't know", "q4": "hunter2"}


def _search(query: str, mode: Retrieval, k: int) -> list[Chunk]:
    return [Chunk(chunk_id=f"d#s0w{i}", doc="d", text=query) for i in range(k)]


def _answer(question: str, passages: list[Chunk]) -> str:
    return _ANSWERS[next(q.id for q in _QUESTIONS if q.question == question)]


def _run(tmp_path: Path, sqlite_uri: str, *, n: int | None = None, answer: Answer = _answer) -> str:
    settings = Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)  # type: ignore[call-arg]
    pilot = PilotSettings(_env_file=None, dgx_base_url="http://dgx.invalid")  # type: ignore[call-arg]
    project = Project(name="mini-rag", root=tmp_path)
    config = RunConfig(
        retrieval=Retrieval.BM25, k=3, n=n, size=120, overlap=20, collection="MiniRag_x", corpus_hash="abc123"
    )
    return run(
        project, settings, pilot, _QUESTIONS, config=config, answer=answer, search=_search,
        results_dir=tmp_path / "results",
    )  # fmt: skip


def _only_run(sqlite_uri: str) -> Run:
    client = MlflowClient(tracking_uri=sqlite_uri)
    exp = client.get_experiment_by_name("mini-rag/retrieval")
    assert exp is not None
    (found,) = client.search_runs([exp.experiment_id])
    return found


def test_run_logs_project_tag_and_experiment(tmp_path: Path, sqlite_uri: str) -> None:
    run_id = _run(tmp_path, sqlite_uri)

    found = _only_run(sqlite_uri)
    assert found.info.run_id == run_id
    assert found.info.status == "FINISHED"
    assert found.info.run_name == "bm25-k3"
    assert found.data.tags["project"] == "mini-rag"
    assert "smoke" not in found.data.tags
    # q1, q2 correct; q3 IDK -> missing; q4 answer to an unanswerable -> hallucination: 0.5 - 0.25
    assert found.data.metrics["score"] == pytest.approx(0.25)
    assert found.data.metrics["accuracy"] == pytest.approx(0.5)
    assert found.data.params["retrieval"] == "bm25"
    assert found.data.params["collection"] == "MiniRag_x"
    assert found.data.params["corpus_hash"] == "abc123"


def test_f_13_generation_error_marks_run_failed_without_metrics(tmp_path: Path, sqlite_uri: str) -> None:
    calls: list[str] = []

    def failing(question: str, passages: list[Chunk]) -> str:
        calls.append(question)
        if len(calls) == 3:
            raise GenerationError("dgx down")
        return "5050"

    with pytest.raises(GenerationError):
        _run(tmp_path, sqlite_uri, answer=failing)

    found = _only_run(sqlite_uri)
    assert found.info.status == "FAILED"
    assert found.data.metrics == {}


def test_d_15_partial_run_logs_smoke_metrics_only(tmp_path: Path, sqlite_uri: str) -> None:
    _run(tmp_path, sqlite_uri, n=2)

    found = _only_run(sqlite_uri)
    assert "score" not in found.data.metrics
    assert found.data.metrics["smoke_score"] == pytest.approx(1.0)
    assert {"smoke_accuracy", "smoke_hallucination", "smoke_missing"} <= set(found.data.metrics)
    assert found.data.tags["smoke"] == "true"
    assert found.data.params["n"] == "2"
    assert len(found.data.params["questions_hash"]) == 64


def test_u_14_config_hash_tag_identifies_the_config(tmp_path: Path, sqlite_uri: str) -> None:
    _run(tmp_path, sqlite_uri, n=2)
    _run(tmp_path, sqlite_uri, n=2)
    _run(tmp_path, sqlite_uri, n=3)

    client = MlflowClient(tracking_uri=sqlite_uri)
    exp = client.get_experiment_by_name("mini-rag/retrieval")
    assert exp is not None
    hashes = [r.data.tags["config_hash"] for r in client.search_runs([exp.experiment_id], order_by=["start_time"])]
    assert hashes[0] == hashes[1] != hashes[2]


@pytest.mark.parametrize("n", [0, 5])
def test_n_outside_the_question_set_is_refused(tmp_path: Path, sqlite_uri: str, n: int) -> None:
    with pytest.raises(ValueError, match="n must be"):
        _run(tmp_path, sqlite_uri, n=n)


def test_per_question_results_are_logged_as_artifact(tmp_path: Path, sqlite_uri: str) -> None:
    run_id = _run(tmp_path, sqlite_uri)

    client = MlflowClient(tracking_uri=sqlite_uri)
    local = Path(client.download_artifacts(run_id, "per_question.json", str(tmp_path)))
    text = local.read_text(encoding="utf-8")
    assert '"q4"' in text
    assert '"hallucination"' in text


def _jsonl_rows(tmp_path: Path) -> list[dict[str, object]]:
    (sink,) = (tmp_path / "results").glob("*.jsonl")
    return [json.loads(line) for line in sink.read_text(encoding="utf-8").splitlines()]


def test_f_13_mlflow_failure_after_answers_keeps_results_locally(
    tmp_path: Path, sqlite_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*_: object, **__: object) -> None:
        raise MlflowException("down")

    monkeypatch.setattr("mini_rag.run.mlflow.log_metrics", down)

    with pytest.raises(MlflowException):
        _run(tmp_path, sqlite_uri)

    rows = _jsonl_rows(tmp_path)
    assert len(rows) == 4
    assert [r["id"] for r in rows] == ["q1", "q2", "q3", "q4"]
    assert rows[3]["prediction"] == "hunter2"


def test_f_13_generation_error_keeps_earlier_answers(tmp_path: Path, sqlite_uri: str) -> None:
    def failing_on_q3(question: str, passages: list[Chunk]) -> str:
        if question == _QUESTIONS[2].question:
            raise GenerationError("dgx down")
        return _answer(question, passages)

    with pytest.raises(GenerationError):
        _run(tmp_path, sqlite_uri, answer=failing_on_q3)

    assert [r["id"] for r in _jsonl_rows(tmp_path)] == ["q1", "q2"]
