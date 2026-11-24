"""One live call end to end (needs `docker compose --profile voice up -d livekit` and the worker running).

Costs a few cents: the booking agent and the simulated caller both use OpenRouter.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from datalab.project import repo_root
from voice_arch import naturalness
from voice_arch.arch import Arch
from voice_arch.call import Outcome, run_one_call
from voice_arch.call_env import CallerHandle
from voice_arch.livekit_env import LiveKitCallEnv
from voice_arch.openrouter_key import key_usage
from voice_arch.personas import Persona, load_personas
from voice_arch.result import CallResult
from voice_arch.settings import VoiceSettings

pytestmark = pytest.mark.integration

PROJECT_DIR = Path(__file__).resolve().parents[2]


class RecordingEnv(LiveKitCallEnv):
    """The real env, keeping the `CallResult` the caller receives so the test can read the raw report."""

    def __init__(self, settings: VoiceSettings) -> None:
        super().__init__(settings)
        self.results: list[CallResult] = []

    async def connect_caller(self, room: str, persona: Persona, arch: Arch) -> CallerHandle:
        handle = await super().connect_caller(room, persona, arch)
        seen = self.results
        original = handle.wait_result

        async def wait_result(timeout: float) -> CallResult | None:
            result = await original(timeout)
            if result is not None and result not in seen:
                seen.append(result)
            return result

        handle.wait_result = wait_result  # type: ignore[method-assign]  # test-only spy on the real handle
        return handle


@pytest.fixture
def live() -> VoiceSettings:
    # Pydantic-settings kwarg.
    return VoiceSettings(_env_file=(repo_root() / ".env", PROJECT_DIR / ".env"))  # pyright: ignore[reportCallIssue]  # _env_file is a pydantic-settings init kwarg the type stub omits


async def test_one_live_call_produces_a_row(
    live: VoiceSettings, record_property: Callable[[str, object], None]
) -> None:
    persona = next(p for p in load_personas(PROJECT_DIR / "data" / "personas.jsonl") if p.id == "self_correction")
    key = live.openrouter_api_key.get_secret_value()
    env = RecordingEnv(live)
    before = key_usage(key).usage

    row = await run_one_call(
        env, persona, Arch.A, "live-one-call", 0,
        call_timeout_s=live.call_timeout_s, join_timeout_s=live.agent_join_timeout_s,
    )  # fmt: skip

    cost = key_usage(key).usage - before
    record_property("outcome", row.outcome.value)
    record_property("cost_usd", f"{cost:.4f}")
    record_property("latencies", str(row.latencies))
    print(f"live call: outcome={row.outcome.value} exact={row.exact} latencies={row.latencies} cost={cost:.4f} $")
    assert row.outcome in {Outcome.SCORED, Outcome.TIMEOUT}
    if row.outcome is Outcome.SCORED:
        (result,) = env.results
        assert result.report is not None
        assert naturalness.latencies(result.report), "no assistant turn in the report"
        naturalness.long_silences(result.report)
        naturalness.barge_ins(result.report)
        assert row.record == result.record
