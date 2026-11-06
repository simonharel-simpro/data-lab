"""Stage-1 bench: `uv run python -m voice_arch.bench --component stt|tts|llm [--n N]`, one MLflow run each.

Run stt, then tts (its judge is the STT default, i.e. the stt winner), then llm.
"""

import argparse
import asyncio
import dataclasses
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
import mlflow
from mlflow import MlflowClient

from datalab.project import Project, load
from datalab.settings import Settings
from datalab.tracking import preflight, tracked_run
from voice_arch import audio
from voice_arch.bench_runs import LlmCase, load_llm_cases, run_llm, run_stt, run_tts
from voice_arch.budget import check_budget, spent_so_far
from voice_arch.candidates import (
    CORPUS_TTS_MODEL,
    CORPUS_VOICE,
    LLM_CANDIDATES,
    STT_CANDIDATES,
    TTS_CANDIDATES,
)
from voice_arch.corpus import Corpus, Utterance, build_corpus, load_utterances
from voice_arch.openrouter_key import SpendTracker
from voice_arch.seams import ChatModel, Synthesizer, Transcriber
from voice_arch.settings import VoiceSettings
from voice_arch.winners import (
    Choice,
    LlmRow,
    NoEligibleCandidate,
    SttRow,
    TtsRow,
    pick_llm,
    pick_stt,
    pick_tts,
)

ESTIMATE_USD: Final = 2.0  # what one component run may cost; F-4b refuses to start when it would reach the budget
TTS_REPS: Final = 3


@dataclass(frozen=True)
class BenchEnv:
    project: Project
    dl: Settings
    voice: VoiceSettings
    results_dir: Path
    key_client: httpx.Client | None = None


@dataclass(frozen=True)
class Outcome:
    rows: Sequence[SttRow | TtsRow | LlmRow]
    metrics: Mapping[str, float]
    choice: Choice | None
    reason: str
    params: Mapping[str, str | int]


def select[T](items: list[T], n: int | None) -> list[T]:
    """The first `n` items; `n` outside 1..len is refused, never clamped."""
    if n is None:
        return items
    if not 1 <= n <= len(items):
        raise ValueError(f"n must be between 1 and {len(items)}, got {n}")
    return items[:n]


def _slug(model: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "_", model)


def _record(outcome: Outcome, sink: Path) -> None:
    mlflow.log_params(outcome.params)
    mlflow.log_metrics(dict(outcome.metrics))
    mlflow.set_tags({"winner": outcome.choice.model if outcome.choice else "none", "winner_reason": outcome.reason})
    sink.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dataclasses.asdict(row)) for row in outcome.rows]
    sink.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _logged_run(
    env: BenchEnv, component: str, params: Mapping[str, str | int], measure: Callable[[], Awaitable[Outcome]]
) -> str:
    """Budget gate, then one run with the spend tracker inside it; a 401/402 propagates: run FAILED (F-4, F-4b)."""
    client = MlflowClient(env.dl.mlflow_tracking_uri)
    check_budget(spent_so_far(client), ESTIMATE_USD, env.voice.experiment_budget_usd)
    key = env.voice.openrouter_api_key.get_secret_value()
    on_exit = lambda cost: mlflow.log_metric("cost_usd", cost)  # noqa: E731
    with (
        tracked_run(env.project, env.dl, run_name=component, sub="bench") as run_id,
        SpendTracker(key, client=env.key_client, on_exit=on_exit),
    ):
        mlflow.log_params(params)
        _record(await measure(), env.results_dir / f"{run_id}.jsonl")
    return run_id


async def bench_stt(
    env: BenchEnv,
    stts: Mapping[str, Transcriber],
    utterances: list[Utterance],
    make_corpus: Callable[[], Awaitable[Corpus]],
) -> str:
    async def measure() -> Outcome:
        corpus = await make_corpus()  # synthesised inside the run, so its cost is attributed
        rows = await run_stt(stts, corpus, utterances)
        metrics = {f"stt_{_slug(r.model)}_{k}": v for r in rows for k, v in (("errors", r.errors), ("p50_s", r.p50_s))}
        choice = pick_stt(rows)
        return Outcome(rows, metrics, choice, choice.reason, {"corpus_hash": corpus.hash})

    params = {"candidates": ",".join(stts), "n": len(utterances), "corpus_tts_model": CORPUS_TTS_MODEL}
    return await _logged_run(env, "stt", params, measure)


async def bench_tts(env: BenchEnv, ttss: Mapping[str, Synthesizer], lines: list[str], judge: Transcriber) -> str:
    async def measure() -> Outcome:
        rows = await run_tts(ttss, lines, judge, TTS_REPS)
        metrics = {
            f"tts_{_slug(r.model)}_{k}": v
            for r in rows
            for k, v in (("ttfb_p50_s", r.ttfb_p50_s), ("intelligible", r.intelligible))
        }
        try:
            choice, reason = pick_tts(rows), ""
        except NoEligibleCandidate as err:
            choice, reason = None, str(err)
        return Outcome(rows, metrics, choice, choice.reason if choice else reason, {})

    params = {"candidates": ",".join(ttss), "n": len(lines), "reps": TTS_REPS, "judge_stt": judge.model}
    return await _logged_run(env, "tts", params, measure)


async def bench_llm(env: BenchEnv, llms: Mapping[str, ChatModel], cases: list[LlmCase]) -> str:
    async def measure() -> Outcome:
        rows = await run_llm(llms, cases)
        metrics = {
            f"llm_{_slug(r.model)}_{k}": v
            for r in rows
            for k, v in (("correct", r.correct), ("ttft_p50_s", r.ttft_p50_s))
        }
        choice = pick_llm(rows)
        return Outcome(rows, metrics, choice, choice.reason, {})

    params = {"candidates": ",".join(llms), "n": len(cases), "llm_providers": "none", "temperature": 0}
    return await _logged_run(env, "llm", params, measure)


async def _dispatch(env: BenchEnv, component: str, n: int | None) -> str:
    data = env.project.root / "data"
    voice = env.voice
    if component == "stt":
        utterances = select(load_utterances(data / "utterances.jsonl"), n)
        corpus_tts = audio.make_tts(voice, CORPUS_TTS_MODEL, CORPUS_VOICE)

        def make_corpus() -> Awaitable[Corpus]:
            return build_corpus(utterances, corpus_tts, data / "audio", tts_model=CORPUS_TTS_MODEL, voice=CORPUS_VOICE)

        stts = {m: audio.make_stt(voice, m) for m in STT_CANDIDATES}
        return await bench_stt(env, stts, utterances, make_corpus)
    if component == "tts":
        lines = select([x for x in (data / "agent_lines.txt").read_text().splitlines() if x.strip()], n)
        ttss = {m: audio.make_tts(voice, m, v) for m, v in TTS_CANDIDATES}
        return await bench_tts(env, ttss, lines, audio.make_stt(voice))
    cases = select(load_llm_cases(data / "llm_cases.jsonl"), n)
    return await bench_llm(env, {m: audio.make_llm(voice, m) for m in LLM_CANDIDATES}, cases)


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="voice_arch.bench", description="Stage-1 bench, logged to MLflow.")
    parser.add_argument("--component", choices=["stt", "tts", "llm"], required=True)
    parser.add_argument("--n", type=int, help="first N items only (a smoke run)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    voice, dl, project = VoiceSettings(), Settings(), load()  # config validated before any I/O  # pyright: ignore[reportCallIssue]
    preflight(dl.mlflow_tracking_uri)
    env = BenchEnv(project, dl, voice, project.root / "results")
    print(asyncio.run(_dispatch(env, args.component, args.n)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
