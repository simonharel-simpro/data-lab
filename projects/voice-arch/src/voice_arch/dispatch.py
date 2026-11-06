"""`python -m voice_arch.dispatch --arch a|b|c --room R` dispatches the booking agent into a room (Phase 2 worker)."""

import argparse
import asyncio
import json
from urllib.parse import urlsplit, urlunsplit

from livekit.api import CreateAgentDispatchRequest, LiveKitAPI

from voice_arch.settings import VoiceSettings

AGENT_NAME = "booking-agent"


def http_url(ws_url: str) -> str:
    """The API speaks http(s); the settings hold the ws(s) form the agents use."""
    parts = urlsplit(ws_url)
    return urlunsplit(parts._replace(scheme="https" if parts.scheme == "wss" else "http"))


async def dispatch(settings: VoiceSettings, arch: str, room: str) -> str:
    request = CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room, metadata=json.dumps({"arch": arch}))
    async with LiveKitAPI(
        url=http_url(settings.livekit_url),
        api_key=settings.livekit_api_key.get_secret_value(),
        api_secret=settings.livekit_api_secret.get_secret_value(),
    ) as api:
        created = await api.agent_dispatch.create_dispatch(request)
    return created.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice_arch.dispatch", description="Dispatch the booking agent.")
    parser.add_argument("--arch", choices=["a", "b", "c"], required=True)
    parser.add_argument("--room", required=True)
    args = parser.parse_args(argv)
    print(asyncio.run(dispatch(VoiceSettings(), args.arch, args.room)))  # pyright: ignore[reportCallIssue]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
