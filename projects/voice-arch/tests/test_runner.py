import json
import shutil
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import cast

import httpx
import pytest
from livekit.agents import llm
from mlflow import MlflowClient
from mlflow.entities import Run

from datalab.project import Project
from datalab.settings import Settings
from tests.call_fakes import SHIPPED, FakeEnv, FakeHandle, FakeTracker, persona, result_for
from tests.fakes import FakeLlm
from voice_arch.arch import Arch
from voice_arch.budget import BudgetExceeded
from voice_arch.call import AgentNeverJoined, ProviderAuthStop
from voice_arch.caller import make_caller_session
from voice_arch.openrouter_key import SpendTracker
from voice_arch.personas import load_personas
from voice_arch.runner import CallerFaultRate, run_sweep
from voice_arch.settings import VoiceSettings

EXPERIMENT = "voice-arch/conversations"
NO_FULL_COST: Callable[[], float | None] = lambda: None  # noqa: E731


class Sweep:
    def __init__(self, tmp_path: Path, sqlite_uri: str, settings: VoiceSettings) -> None:
        self.project = Project(name="voice-arch", root=tmp_path)
        self.dl = Settings(mlflow_tracking_uri=sqlite_uri)
        self.settings = settings
        self.client = MlflowClient(sqlite_uri)
        self.tmp = tmp_path

    async def run(
        self,
        env: FakeEnv,
        personas: list[str],
        reps: int,
        *,
        spent: float = 0.0,
        last_full: Callable[[], float | None] = NO_FULL_COST,
        tracker: Callable[..., FakeTracker] | None = None,
    ) -> str:
        chosen = [p for p in load_personas(SHIPPED) if p.id in personas]
        factory = tracker or partial(FakeTracker)
        return await run_sweep(
            env, chosen, Arch.A, reps, self.settings, project=self.project, dl_settings=self.dl,
            spent=spent, last_full_cost=last_full, spend_tracker=factory,
        )  # fmt: skip

    def only_run(self) -> Run:
        experiment = self.client.get_experiment_by_name(EXPERIMENT)
        assert experiment is not None
        (run,) = self.client.search_runs([experiment.experiment_id])
        return run

    def rows(self, run: Run) -> list[dict[str, object]]:
        path = self.tmp / "results" / f"{run.info.run_id}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture(scope="session")
def _migrated_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MLflow migrates a fresh sqlite file for ~7 s: do it once and hand every test a copy."""
    path = tmp_path_factory.mktemp("mlflow-template") / "template.db"
    MlflowClient(f"sqlite:///{path}").search_experiments()
    return path


@pytest.fixture
def sqlite_uri(tmp_path: Path, _migrated_db: Path) -> str:
    shutil.copy(_migrated_db, tmp_path / "mlflow.db")
    return f"sqlite:///{tmp_path / 'mlflow.db'}"


@pytest.fixture
def sweep(tmp_path: Path, sqlite_uri: str, voice_settings: VoiceSettings) -> Sweep:
    return Sweep(tmp_path, sqlite_uri, voice_settings)


async def test_f_2_sweep_aborts_when_no_agent_joins_within_deadline(sweep: Sweep) -> None:
    env = FakeEnv([FakeHandle(joins=False)])

    with pytest.raises(AgentNeverJoined):
        await sweep.run(env, ["self_correction", "speller"], reps=2)

    assert sweep.only_run().info.status == "FAILED"
    assert len(env.rooms) == 1


async def test_f_4_402_aborts_sweep_and_creates_no_further_rooms(sweep: Sweep) -> None:
    who = persona()
    env = FakeEnv([FakeHandle(result_for(who, http_status=402))])

    with pytest.raises(ProviderAuthStop):
        await sweep.run(env, ["self_correction", "speller"], reps=2)

    assert sweep.only_run().info.status == "FAILED"
    assert len(env.rooms) == 1


async def test_f_6_more_than_10_percent_caller_faults_fails_the_run(sweep: Sweep) -> None:
    who = persona()
    faulty = [FakeHandle(result_for(who), caller_error="tts 500") for _ in range(2)]
    env = FakeEnv(faulty)

    with pytest.raises(CallerFaultRate):
        await sweep.run(env, ["self_correction", "speller"], reps=5)

    run = sweep.only_run()
    assert run.info.status == "FAILED"
    assert len(sweep.rows(run)) == 10
    assert run.data.metrics["smoke_n_caller_fault"] == 2


async def test_exactly_10_percent_caller_faults_is_tolerated(sweep: Sweep) -> None:
    env = FakeEnv([FakeHandle(result_for(persona()), caller_error="tts 500")])

    await sweep.run(env, ["self_correction", "speller"], reps=5)

    assert sweep.only_run().info.status == "FINISHED"


async def test_budget_exceeded_mid_sweep_stops_before_next_call(sweep: Sweep) -> None:
    after_first_call, final_cost = 5.5, 5.7
    tracker = partial(FakeTracker, readings=[after_first_call], final=final_cost)

    with pytest.raises(BudgetExceeded):
        await sweep.run(
            FakeEnv(), ["self_correction", "speller"], 2, spent=45.0, last_full=lambda: 4.0, tracker=tracker
        )

    run = sweep.only_run()
    assert run.info.status == "FAILED"
    assert len(sweep.rows(run)) == 1
    assert run.data.metrics["cost_usd"] == final_cost


async def test_budget_exceeded_runs_one_room_only(sweep: Sweep) -> None:
    env = FakeEnv()
    tracker = partial(FakeTracker, readings=[9.0])

    with pytest.raises(BudgetExceeded):
        await sweep.run(env, ["self_correction"], 3, spent=45.0, last_full=lambda: 4.0, tracker=tracker)

    assert len(env.rooms) == 1


async def test_sweep_refused_when_estimate_reaches_budget(sweep: Sweep) -> None:
    env = FakeEnv()

    with pytest.raises(BudgetExceeded):
        await sweep.run(env, ["self_correction"], 1, spent=45.0)

    assert env.rooms == []
    assert sweep.client.get_experiment_by_name(EXPERIMENT) is None


async def test_u_1_sweep_with_fewer_reps_than_full_logs_smoke_metrics_only(sweep: Sweep) -> None:
    await sweep.run(FakeEnv(), ["self_correction"], reps=1)

    run = sweep.only_run()
    assert run.info.status == "FINISHED"
    assert run.data.tags["full"] == "false"
    assert run.data.metrics["smoke_exact_rate"] == 1.0
    assert all(key.startswith("smoke_") for key in run.data.metrics)


async def test_full_sweep_logs_unprefixed_metrics_and_the_full_tag(sweep: Sweep) -> None:
    ids = [p.id for p in load_personas(SHIPPED)]

    await sweep.run(FakeEnv(), ids, reps=5)

    run = sweep.only_run()
    assert run.data.tags["full"] == "true"
    assert run.data.metrics["exact_rate"] == 1.0
    assert run.data.metrics["n_scored"] == len(ids) * 5
    assert len(sweep.rows(run)) == len(ids) * 5


async def test_cost_is_logged_with_cost_per_call(sweep: Sweep) -> None:
    final = 0.6
    tracker = partial(FakeTracker, final=final)

    await sweep.run(FakeEnv(), ["self_correction"], reps=2, tracker=tracker)

    metrics = sweep.only_run().data.metrics
    assert metrics["cost_usd"] == final
    assert metrics["cost_per_call_usd"] == pytest.approx(final / 2)


async def test_f_12_cost_absent_when_key_read_fails(sweep: Sweep) -> None:
    reads = iter([200, 500, 500, 500])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(reads)
        return httpx.Response(status, json={"data": {"usage": 1.0}} if status == 200 else {})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    await sweep.run(FakeEnv(), ["self_correction"], 1, tracker=partial(SpendTracker, client=client))

    run = sweep.only_run()
    assert run.info.status == "FINISHED"
    assert "cost_usd" not in run.data.metrics


async def test_u_20_caller_llm_uses_configured_model_and_temperature(sweep: Sweep) -> None:
    seen: list[tuple[str, float]] = []

    def spy(settings: VoiceSettings, *, model: str, temperature: float, retry_empty: bool) -> llm.LLM:
        seen.append((model, temperature))
        return cast("llm.LLM", FakeLlm(lambda _text: None))

    make_caller_session(sweep.settings, llm_factory=spy)
    await sweep.run(FakeEnv(), ["self_correction"], reps=1)

    expected = (sweep.settings.caller_llm_model, sweep.settings.caller_temperature)
    assert seen == [expected]
    params = sweep.only_run().data.params
    assert (params["caller_llm_model"], float(params["caller_temperature"])) == expected


async def test_params_record_the_worker_config_from_the_first_result(sweep: Sweep) -> None:
    await sweep.run(FakeEnv(), ["self_correction"], reps=1)

    params = sweep.only_run().data.params
    assert params["arch"] == Arch.A.value
    assert params["max_tool_steps"] == "6"
    assert params["reps"] == "1"
    assert (params["llm_providers"], params["caller_llm_providers"]) == ("google-vertex,google-ai-studio", "none")
    assert params["personas"] == "self_correction"
