"""One pilot run: answer every selected question, score, and log to MLflow (`mini-rag/retrieval`).

`uv run python -m mini_rag.run --retrieval bm25|vector --k 3|5 [--n N]` from `projects/mini-rag`.
"""

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import mlflow

from datalab.project import Project, load
from datalab.settings import Settings, connect_weaviate
from datalab.tracking import preflight, tracked_run
from mini_rag.corpus import OVERLAP, SIZE, Chunk, load_corpus
from mini_rag.generate import LlmGenerator
from mini_rag.index import Retrieval, corpus_hash, ensure_collection, search
from mini_rag.questions import Question, load_questions
from mini_rag.scoring import Outcome, metrics, outcome
from mini_rag.settings import PilotSettings, is_openrouter, public_url

Answer = Callable[[str, list[Chunk]], str]
Search = Callable[[str, Retrieval, int], list[Chunk]]


@dataclass(frozen=True)
class Result:
    id: str
    prediction: str
    expected: str | None
    outcome: Outcome
    chunk_ids: list[str]


@dataclass(frozen=True)
class RunConfig:
    """What identifies a run's setup; logged as params and covered by config_hash."""

    retrieval: Retrieval
    k: int
    n: int | None
    size: int
    overlap: int
    collection: str
    corpus_hash: str


def _select(questions: list[Question], n: int | None) -> list[Question]:
    """The first `n` questions in file order; `n` outside 1..len is refused, never clamped."""
    if n is None:
        return questions
    if not 1 <= n <= len(questions):
        raise ValueError(f"n must be between 1 and {len(questions)}, got {n}")
    return questions[:n]


def _sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _answer_all(
    selected: list[Question], retrieval: Retrieval, k: int, answer: Answer, find: Search, sink: Path
) -> list[Result]:
    """Each scored answer is appended to `sink` at once: the crash copy survives a kill or an MLflow outage."""
    sink.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for q in selected:
        passages = find(q.question, retrieval, k)
        prediction = answer(q.question, passages)  # a GenerationError propagates: run FAILED, no metrics (F-13)
        ids = [p.chunk_id for p in passages]
        result = Result(q.id, prediction, q.answer, outcome(prediction, q.answer), ids)
        with sink.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result)) + "\n")
        results.append(result)
    return results


def run(
    project: Project,
    settings: Settings,
    pilot: PilotSettings,
    questions: list[Question],
    *,
    config: RunConfig,
    answer: Answer,
    search: Search,
    results_dir: Path,
    served_by: Callable[[], Mapping[str, int]] | None = None,
) -> str:
    """Returns the run id. Metrics are logged once, after every question is scored (F-13)."""
    selected = _select(questions, config.n)
    partial = len(selected) < len(questions)  # D-15: a subset logs smoke_* only, never `score`
    params = {"retrieval": str(config.retrieval), "k": config.k, "n": config.n}
    params |= {"questions_hash": _sha256([q.id for q in selected])}
    params |= {"llm_base_url": public_url(pilot.llm_base_url), "llm_providers": _routing(pilot)}
    params |= {"gen_model": pilot.gen_model, "max_tokens": pilot.max_tokens}
    params |= {"size": config.size, "overlap": config.overlap, "collection": config.collection}
    params |= {"corpus_hash": config.corpus_hash}
    tags = {"config_hash": _sha256(params)} | ({"smoke": "true"} if partial else {})
    name = f"{config.retrieval}-k{config.k}"
    with tracked_run(project, settings, run_name=name, sub="retrieval", tags=tags) as run_id:
        mlflow.log_params(params)
        sink = results_dir / f"{run_id}.jsonl"
        results = _answer_all(selected, config.retrieval, config.k, answer, search, sink)
        mlflow.log_metrics(metrics([r.outcome for r in results]).as_dict(prefix="smoke_" if partial else ""))
        mlflow.log_dict({"results": [asdict(r) for r in results]}, "per_question.json")
        if served_by is not None and (counts := served_by()):
            mlflow.set_tag("llm_served_by", json.dumps(dict(counts), sort_keys=True))
    return run_id


def _routing(pilot: PilotSettings) -> str:
    """The OpenRouter provider allow-list and quantization, as logged; "none" for another endpoint."""
    if not is_openrouter(pilot.llm_base_url):
        return "none"
    return f"{pilot.openrouter_providers}@{pilot.openrouter_quantization}"


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return value


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mini_rag.run", description="One mini-rag run, logged to MLflow.")
    parser.add_argument("--retrieval", type=Retrieval, choices=list(Retrieval), required=True)
    parser.add_argument("--k", type=_positive_int, required=True, help="passages retrieved per question")
    parser.add_argument("--n", type=int, help="first N questions only: a smoke run (smoke_* metrics, D-15)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    project, pilot, settings = load(), PilotSettings(), Settings()  # config validated before any I/O (F-13)
    questions = load_questions(project.root / "data" / "questions.jsonl")
    chunks = load_corpus(project.root / "data" / "corpus", size=SIZE, overlap=OVERLAP)
    preflight(settings.mlflow_tracking_uri)
    key = pilot.llm_api_key.get_secret_value() if pilot.llm_api_key else None
    openrouter = is_openrouter(pilot.llm_base_url)
    generator = LlmGenerator(
        pilot.llm_base_url, pilot.gen_model, api_key=key, timeout_s=pilot.gen_timeout_s, max_tokens=pilot.max_tokens,
        providers=pilot.provider_list if openrouter else None,
        quantization=pilot.openrouter_quantization if openrouter else None,
    )  # fmt: skip
    corpus = corpus_hash(chunks)
    with connect_weaviate(settings) as client:
        name = ensure_collection(client, chunks, size=SIZE, overlap=OVERLAP, corpus=corpus)
        config = RunConfig(args.retrieval, args.k, args.n, SIZE, OVERLAP, name, corpus)
        run_id = run(
            project, settings, pilot, questions, config=config, answer=generator.answer,
            search=lambda query, mode, k: search(client, name, query, mode, k),
            results_dir=project.root / "results", served_by=lambda: generator.served,
        )  # fmt: skip
    print(f"run {run_id} ({args.retrieval}-k{args.k}) logged to {settings.mlflow_tracking_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
