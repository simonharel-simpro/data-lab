"""Architecture A: one agent holding every instruction and every tool."""

from livekit.agents import Agent

from voice_arch.agents.state import session_of
from voice_arch.agents.tools import ALL_TOOLS
from voice_arch.booking import instructions as text

INSTRUCTIONS = " ".join(
    (
        text.CONTEXT,
        text.GREETING,
        text.ASK_NAME,
        text.ASK_PHONE,
        text.ASK_ADDRESS,
        text.ASK_PROBLEM,
        text.ASK_SLOT,
        text.CONFIRM,
    )
)


class OrchestratorAgent(Agent):
    def __init__(self) -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]  # Agent.__init__ takes STT[Unknown]
            instructions=INSTRUCTIONS, tools=list(ALL_TOOLS)
        )

    async def on_enter(self) -> None:
        # Only the booking agent greets (F-8): the caller waits for this first turn.
        session_of(self).generate_reply(instructions=text.GREETING)
