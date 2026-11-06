"""`python -m voice_arch.token --room R [--identity me] [--agent NAME]` prints a LiveKit join token."""

import argparse

from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants

from voice_arch.settings import VoiceSettings


def make_token(settings: VoiceSettings, room: str, identity: str, agent: str | None = None) -> str:
    """A join token for `room`; with `agent`, joining also dispatches that agent into the room."""
    if not room:
        raise ValueError("room must not be empty")
    token = (
        AccessToken(settings.livekit_api_key.get_secret_value(), settings.livekit_api_secret.get_secret_value())
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room))
    )
    if agent is not None:
        token = token.with_room_config(RoomConfiguration(agents=[RoomAgentDispatch(agent_name=agent)]))
    return token.to_jwt()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice_arch.token", description="Print a LiveKit join token.")
    parser.add_argument("--room", required=True)
    parser.add_argument("--identity", default="me")
    parser.add_argument("--agent", help="agent name to dispatch into the room when the token joins")
    args = parser.parse_args(argv)
    print(make_token(VoiceSettings(), args.room, args.identity, args.agent))  # pyright: ignore[reportCallIssue]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
