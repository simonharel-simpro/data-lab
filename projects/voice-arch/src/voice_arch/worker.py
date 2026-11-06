"""`uv run python -m voice_arch.worker dev|start`: the booking agent worker (agent name `booking-agent`).

One job = one call: build the session, run the chosen architecture until the session closes, then send one
`CallResult` to the room (the runner reads it) before returning. Nothing is written to disk.
"""

import logging
from typing import Final

from livekit import rtc
from livekit.agents import AgentServer, AgentSession, JobContext, cli
from livekit.plugins import silero

from voice_arch.agents.arch_b import SUMMARIZE_CHAT_CTX
from voice_arch.agents.registry import build_agent
from voice_arch.agents.state import BookingState
from voice_arch.arch import Arch, UnknownArchError
from voice_arch.audio import make_llm, make_stt, make_tts
from voice_arch.dispatch import AGENT_NAME
from voice_arch.result import RESULT_TOPIC, CallResult
from voice_arch.settings import VoiceSettings
from voice_arch.worker_logic import (
    MAX_TOOL_STEPS,
    TURN_HANDLING,
    SessionWatch,
    build_result,
    error_result,
    parse_metadata,
)

logger = logging.getLogger("voice_arch.worker")
settings = VoiceSettings()  # pyright: ignore[reportCallIssue]
server = AgentServer(
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key.get_secret_value(),
    api_secret=settings.livekit_api_secret.get_secret_value(),
)
_TASKGROUP_ARCHES: Final = {Arch.B, Arch.C}  # the arches that run a TaskGroup


async def send_result(room: rtc.Room, result: CallResult) -> None:
    """Sent before the job returns (not in `on_session_end`, where the room may be gone); failure is logged."""
    try:
        await room.local_participant.send_text(result.to_json(), topic=RESULT_TOPIC)
    except Exception:  # room already deleted or disconnected: nobody is left to read it
        logger.exception("could not send the call result for room %s", room.name)


async def run_call(ctx: JobContext, arch: Arch) -> tuple[AgentSession[BookingState], SessionWatch]:
    session = AgentSession[BookingState](
        stt=make_stt(settings),
        # PROVISIONAL (ESC-2-1): no provider pin, as in the stage-1 bench: the pinned upstreams serve no gemini.
        llm=make_llm(settings),
        tts=make_tts(settings),
        vad=silero.VAD.load(),
        userdata=BookingState(),
        turn_handling=TURN_HANDLING,
        max_tool_steps=MAX_TOOL_STEPS,
    )
    watch = SessionWatch()
    watch.attach(session)
    await session.start(agent=build_agent(arch), room=ctx.room)
    await watch.closed.wait()
    return session, watch


@server.rtc_session(agent_name=AGENT_NAME)
async def entry(ctx: JobContext) -> None:
    await ctx.connect()
    try:
        arch, run_id = parse_metadata(ctx.job.metadata)
    except UnknownArchError as err:
        logger.error("refusing the dispatch: %s", err)
        await send_result(ctx.room, error_result(ctx.room.name, str(err)))
        return
    session, watch = await run_call(ctx, arch)
    result = build_result(
        ctx.room.name,
        arch,
        run_id,
        session.userdata,
        watch.close,
        watch.errors,
        lambda: ctx.make_session_report(session).to_dict(),
        summarize_chat_ctx=SUMMARIZE_CHAT_CTX if arch in _TASKGROUP_ARCHES else None,
        max_tool_steps=MAX_TOOL_STEPS,
    )
    await send_result(ctx.room, result)


if __name__ == "__main__":
    cli.run_app(server)
