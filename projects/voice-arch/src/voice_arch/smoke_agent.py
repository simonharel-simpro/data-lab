"""Phase-1 media smoke agent: `uv run python -m voice_arch.smoke_agent dev`, then join from the browser."""

import logging

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.agents.voice.events import ConversationItemAddedEvent
from livekit.plugins import silero

from voice_arch.audio import make_llm, make_stt, make_tts
from voice_arch.settings import load_settings

logger = logging.getLogger("voice_arch.smoke")
# Module level: LiveKit pickles the entrypoint by module reference, so `server` cannot be built in a function.
settings = load_settings()
server = AgentServer(
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key.get_secret_value(),
    api_secret=settings.livekit_api_secret.get_secret_value(),
)


@server.rtc_session(agent_name="smoke")
async def entrypoint(ctx: JobContext) -> None:
    session = AgentSession[None](
        stt=make_stt(settings),
        tts=make_tts(settings),
        llm=make_llm(settings),
        vad=silero.VAD.load(),
        turn_handling={"turn_detection": "vad", "interruption": {"mode": "vad"}},
    )

    def _log_latency(event: ConversationItemAddedEvent) -> None:
        item = event.item
        if item.type == "message" and item.role == "assistant":
            logger.info("e2e_latency=%s", item.metrics.get("e2e_latency"))

    session.on("conversation_item_added", _log_latency)  # pyright: ignore[reportUnknownMemberType]  # SDK on()
    agent = Agent(  # pyright: ignore[reportUnknownVariableType]  # Agent.__init__ takes STT[Unknown]
        instructions="You are a friendly test agent. Keep answers short."
    )
    await session.start(agent, room=ctx.room)  # pyright: ignore[reportUnknownMemberType]  # SDK overloads
    await session.generate_reply(instructions="Greet the caller in one short sentence.")


if __name__ == "__main__":
    cli.run_app(server)
