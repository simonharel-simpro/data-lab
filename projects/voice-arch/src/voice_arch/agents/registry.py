"""Maps an `Arch` to the agent that starts the call."""

from typing import assert_never

from livekit.agents import Agent

from voice_arch.agents.arch_a import OrchestratorAgent
from voice_arch.agents.arch_b import BookingFlowAgent
from voice_arch.agents.arch_c import build_task_group_c
from voice_arch.arch import Arch


def build_agent(arch: Arch) -> Agent:
    match arch:
        case Arch.A:
            return OrchestratorAgent()
        case Arch.B:
            return BookingFlowAgent()
        case Arch.C:
            return BookingFlowAgent(build_task_group_c)
        case _:
            assert_never(arch)
