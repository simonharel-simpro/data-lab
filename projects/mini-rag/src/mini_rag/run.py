"""One pilot run: answer every selected question, score, and log to MLflow (`mini-rag/retrieval`).

`uv run python -m mini_rag.run --retrieval bm25|vector --k 3|5 [--n N]` from `projects/mini-rag`.
"""

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

import mlflow

from datalab.project import Project, load
from datalab.settings import Settings, connect_weaviate
from datalab.tracking import preflight, tracked_run
from mini_rag.corpus import OVERLAP, SIZE, Chunk, load_corpus
from mini_rag.generate import DgxGenerator
from mini_rag.index import Retrieval, ensure_collection, search
from mini_rag.questions import Question, load_questions
from mini_rag.scoring import Outcome, metrics, outcome
from mini_rag.settings import PilotSettings

Answer = Callable[[str, list[Chunk]], str]
Search = Callable[[str, Retrieval, int], list[Chunk]]


@dataclass(frozen=True)
class Result:
    id: str
    prediction: str
    expected: str | None
    outcome: Outcome
    chunk_ids: list[str]


def _select(questions: list[Question], n: int | None) -> list[Question]:
    """The first `n` questions in file order; `n` outside 1..len is refused, never clamped."""
    if n is None:
        return questions
    if not 1 <= n <= len(questions):
        raise ValueError(f"n must be between 1 and {len(questions)}, got {n}")
    return questions[:n]


def _sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _answer_all(selected: list[Question], retrieval: Retrieval, k: int, answer: Answer, find: Search) -> list[Result]:
    results = []
    for q in selected:
        passages = find(q.question, retrieval, k)
        prediction = answer(q.question, passages)  # a GenerationError propagates: run FAILED, no metrics (F-13)
        ids = [p.chunk_id for p in passages]
        results.append(Result(q.id, prediction, q.answer, outcome(prediction, q.answer), ids))
    return results


def run(
    project: Project,
    settings: Settings,
    pilot: PilotSettings,
    questions: list[Question],
    *,
    retrieval: Retrieval,
    k: int,
    n: int | None,
    size: int,
    overlap: int,
    collection: str,
    answer: Answer,
    search: Search,
) -> str:
    """Returns the run id. Metrics are logged once, after every question is scored (F-13)."""
    selected = _select(questions, n)
    partial = len(selected) < len(questions)  # D-15: a subset logs smoke_* only, never `score`
    params = {"retrieval": str(retrieval), "k": k, "n": n, "questions_hash": _sha256([q.id for q in selected])}
    params |= {"gen_model": pilot.gen_model, "max_tokens": pilot.max_tokens, "size": size, "overlap": overlap}
    params |= {"collection": collection}
    tags = {"config_hash": _sha256(params)} | ({"smoke": "true"} if partial else {})
    with tracked_run(project, settings, run_name=f"{retrieval}-k{k}", sub="retrieval", tags=tags) as run_id:
        mlflow.log_params(params)
        results = _answer_all(selected, retrieval, k, answer, search)
        mlflow.log_metrics(metrics([r.outcome for r in results]).as_dict(prefix="smoke_" if partial else ""))
        mlflow.log_dict({"results": [r.__dict__ for r in results]}, "per_question.json")
    return run_id


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mini_rag.run", description="One mini-rag run, logged to MLflow.")
    parser.add_argument("--retrieval", type=Retrieval, choices=list(Retrieval), required=True)
    parser.add_argument("--k", type=int, required=True, help="passages retrieved per question")
    parser.add_argument("--n", type=int, help="first N questions only: a smoke run (smoke_* metrics, D-15)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    project, pilot, settings = load(), PilotSettings(), Settings()  # config validated before any I/O (F-13)
    questions = load_questions(project.root / "data" / "questions.jsonl")
    chunks = load_corpus(project.root / "data" / "corpus", size=SIZE, overlap=OVERLAP)
    preflight(settings.mlflow_tracking_uri)
    generator = DgxGenerator(
        pilot.dgx_base_url, pilot.gen_model, timeout_s=pilot.gen_timeout_s, max_tokens=pilot.max_tokens
    )
    with connect_weaviate(settings) as client:
        name = ensure_collection(client, chunks, size=SIZE, overlap=OVERLAP)
        run_id = run(
            project, settings, pilot, questions, retrieval=args.retrieval, k=args.k, n=args.n, size=SIZE,
            overlap=OVERLAP, collection=name, answer=generator.answer,
            search=lambda query, mode, k: search(client, name, query, mode, k),
        )  # fmt: skip
    print(f"run {run_id} ({args.retrieval}-k{args.k}) logged to {settings.mlflow_tracking_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
