import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import httpx
import pytest
from livekit.agents import APIStatusError
from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.project import Project
from datalab.settings import Settings
from tests.fakes import FakeLlm, FakeStt, FakeTts
from voice_arch.bench import BenchEnv, bench_llm, bench_stt, bench_tts
from voice_arch.bench_record import select
from voice_arch.bench_runs import LlmCase
from voice_arch.budget import BudgetExceeded
from voice_arch.corpus import Corpus, Utterance, build_corpus
from voice_arch.settings import VoiceSettings

_UTTERANCES = [
    Utterance("u1", "My name is John Miller.", {"name": "John Miller"}),
    Utterance("u2", "Call me on 415 555 0134.", {"phone": "4155550134"}),
]


def _key_client(usages: list[float], status: int = 200) -> httpx.Client:
    values: Iterator[float] = iter(usages)

    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"data": {"usage": next(values), "limit_remaining": 40.0}})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def env_for(tmp_path: Path, sqlite_uri: str, voice_settings: VoiceSettings) -> Callable[..., BenchEnv]:
    def make(client: httpx.Client | None = None) -> BenchEnv:
        dl = Settings(_env_file=None, mlflow_tracking_uri=sqlite_uri)  # type: ignore[call-arg]
        client = client or _key_client([1.0, 1.4])
        return BenchEnv(Project("voice-arch", tmp_path), dl, voice_settings, tmp_path / "results", client)

    return make


def _runs(env: BenchEnv) -> list[Run]:
    client = MlflowClient(env.dl.mlflow_tracking_uri)
    experiment = client.get_experiment_by_name("voice-arch/bench")
    return [] if experiment is None else list(client.search_runs([experiment.experiment_id]))


def _corpus(tmp_path: Path) -> Callable[[], Awaitable[Corpus]]:
    return lambda: build_corpus(_UTTERANCES, FakeTts(), tmp_path / "audio", tts_model="m", voice="v")


async def test_u_6_bench_never_logs_exact_rate(env_for: Callable[..., BenchEnv], tmp_path: Path) -> None:
    env = env_for()
    stts = {"vendor/good-1": FakeStt(), "vendor/empty": FakeStt(hear=lambda spoken: "")}

    run_id = await bench_stt(env, stts, _UTTERANCES, _corpus(tmp_path))

    (run,) = _runs(env)
    assert run.info.run_id == run_id and run.info.status == "FINISHED"
    assert "exact_rate" not in run.data.metrics
    assert run.data.metrics["stt_vendor_good_1_errors"] == 0
    assert run.data.metrics["stt_vendor_empty_errors"] == 2
    assert run.data.metrics["cost_usd"] == pytest.approx(0.4)
    assert run.data.tags["winner"] == "vendor/good-1"
    assert "errors" in run.data.tags["winner_reason"]
    rows = (env.results_dir / f"{run_id}.jsonl").read_text().splitlines()
    assert [json.loads(r)["model"] for r in rows] == ["vendor/good-1", "vendor/empty"]


async def test_f_4_402_aborts_the_bench(env_for: Callable[..., BenchEnv], tmp_path: Path) -> None:
    env = env_for()
    second = FakeStt()
    stts = {"a/402": FakeStt(error=APIStatusError("payment required", status_code=402)), "b/next": second}

    with pytest.raises(APIStatusError):
        await bench_stt(env, stts, _UTTERANCES, _corpus(tmp_path))

    (run,) = _runs(env)
    assert run.info.status == "FAILED"
    assert second.calls == 0
    assert run.data.metrics["cost_usd"] == pytest.approx(0.4)  # the failed run still records what it spent


async def test_bench_refuses_when_budget_spent(env_for: Callable[..., BenchEnv], tmp_path: Path) -> None:
    env = env_for(_key_client([1.0, 1.0]))
    await bench_stt(env, {"a/x": FakeStt()}, _UTTERANCES, _corpus(tmp_path))
    client = MlflowClient(env.dl.mlflow_tracking_uri)
    (done,) = _runs(env)
    client.log_metric(done.info.run_id, "cost_usd", 49.0)
    spy = FakeStt()

    with pytest.raises(BudgetExceeded):
        await bench_stt(env, {"b/y": spy}, _UTTERANCES, _corpus(tmp_path))

    assert spy.calls == 0
    assert len(_runs(env)) == 1  # no new run was opened


async def test_f_12_unreadable_key_usage_omits_cost_without_failing_the_bench(
    env_for: Callable[..., BenchEnv], tmp_path: Path
) -> None:
    env = env_for(_key_client([], status=500))

    await bench_stt(env, {"a/x": FakeStt()}, _UTTERANCES, _corpus(tmp_path))

    (run,) = _runs(env)
    assert run.info.status == "FINISHED"
    assert "cost_usd" not in run.data.metrics


async def test_bench_tts_without_intelligible_candidate_tags_no_winner(env_for: Callable[..., BenchEnv]) -> None:
    env = env_for()
    ttss = {"v/garbled": FakeTts(say=lambda text: "zzz qqq")}

    await bench_tts(env, ttss, ["Hello there friend."], FakeStt())

    (run,) = _runs(env)
    assert run.info.status == "FINISHED"
    assert run.data.tags["winner"] == "none"
    assert "intelligible" in run.data.tags["winner_reason"]
    assert run.data.metrics["tts_v_garbled_intelligible"] == 0


async def test_bench_llm_logs_correct_and_ttft_per_candidate(env_for: Callable[..., BenchEnv]) -> None:
    env = env_for()
    cases = [LlmCase("n01", "My name is John Miller.", "record_name", {"name": "John Miller"})]
    llms = {"v/m-1": FakeLlm(lambda caller: ("record_name", json.dumps({"name": "John Miller"})), first_delay_s=0.01)}

    await bench_llm(env, llms, cases)

    (run,) = _runs(env)
    assert run.data.metrics["llm_v_m_1_correct"] == 1
    assert run.data.metrics["llm_v_m_1_ttft_p50_s"] >= 0.01
    assert run.data.tags["winner"] == "v/m-1"


def test_select_refuses_out_of_range_n() -> None:
    assert select([1, 2, 3], None) == [1, 2, 3]
    assert select([1, 2, 3], 2) == [1, 2]
    for bad in (0, 4):
        with pytest.raises(ValueError, match="n must be between 1 and 3"):
            select([1, 2, 3], bad)


async def test_bench_crash_keeps_earlier_candidate_rows(env_for: Callable[..., BenchEnv], tmp_path: Path) -> None:
    env = env_for()
    stts = {"a/ok": FakeStt(), "b/402": FakeStt(error=APIStatusError("payment required", status_code=402))}

    with pytest.raises(APIStatusError):
        await bench_stt(env, stts, _UTTERANCES, _corpus(tmp_path))

    (run,) = _runs(env)
    assert run.info.status == "FAILED"
    lines = (env.results_dir / f"{run.info.run_id}.jsonl").read_text().splitlines()
    assert [json.loads(line)["model"] for line in lines] == ["a/ok"]
