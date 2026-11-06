"""The seam the runner is tested through: everything that touches LiveKit sits behind these two protocols (D-9)."""

from typing import Protocol

from voice_arch.arch import Arch
from voice_arch.personas import Persona
from voice_arch.result import CallResult


class CallerHandle(Protocol):
    agent_left: bool
    caller_http_status: int | None
    caller_error: str | None

    async def wait_agent(self, timeout: float) -> bool: ...

    async def wait_result(self, timeout: float) -> CallResult | None:
        """The agent's result, or None when none arrived within `timeout` seconds."""
        ...

    async def interject(self, text: str) -> None: ...

    def agent_speaking_for(self) -> float:
        """Seconds the booking agent has been speaking without a break; 0.0 when it is not speaking."""
        ...

    async def close(self) -> None: ...


class CallEnv(Protocol):
    async def create_dispatch(self, room: str, arch: Arch, run_id: str) -> None: ...

    async def connect_caller(self, room: str, persona: Persona, arch: Arch) -> CallerHandle: ...

    async def delete_room(self, room: str) -> None: ...
