"""The real `CallEnv`: LiveKit rooms, agent dispatch and the caller session (D-9)."""

import logging
from typing import Final

from livekit import rtc
from livekit.api import DeleteRoomRequest, LiveKitAPI

from voice_arch.arch import Arch
from voice_arch.call_env import CallerHandle
from voice_arch.caller import CallerAgent, make_caller_session
from voice_arch.dispatch import dispatch, http_url
from voice_arch.live_caller import LiveCaller
from voice_arch.personas import Persona
from voice_arch.settings import VoiceSettings
from voice_arch.token import make_token

logger = logging.getLogger(__name__)
_CALLER_IDENTITY: Final = "simulated-caller"
_LISTEN_AFTER: Final = {Arch.A: 0, Arch.B: 1, Arch.C: 1}  # see LiveCaller


class LiveKitCallEnv:
    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings

    async def create_dispatch(self, room: str, arch: Arch, run_id: str) -> None:
        await dispatch(self._settings, arch.value, room, run_id)

    async def connect_caller(self, room: str, persona: Persona, arch: Arch) -> CallerHandle:
        lk_room = rtc.Room()
        caller = LiveCaller(lk_room, make_caller_session(self._settings), _LISTEN_AFTER[arch])
        token = make_token(self._settings, room, _CALLER_IDENTITY)
        try:
            await lk_room.connect(self._settings.livekit_url, token)
        except Exception:  # release the half-open caller, then re-raise the original failure
            await caller.close()
            raise
        caller.scan()
        caller.start(CallerAgent(persona.instructions))
        return caller

    async def delete_room(self, room: str) -> None:
        async with LiveKitAPI(
            url=http_url(self._settings.livekit_url),
            api_key=self._settings.livekit_api_key.get_secret_value(),
            api_secret=self._settings.livekit_api_secret.get_secret_value(),
        ) as api:
            await api.room.delete_room(DeleteRoomRequest(room=room))
