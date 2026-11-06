import jwt
import pytest

from voice_arch.settings import VoiceSettings
from voice_arch.token import make_token


def _decode(token: str, settings: VoiceSettings) -> dict[str, dict[str, object]]:
    return jwt.decode(
        token,
        settings.livekit_api_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )


def test_make_token_carries_room_and_agent_dispatch(voice_settings: VoiceSettings) -> None:
    claims = _decode(make_token(voice_settings, "r", "me", agent="smoke"), voice_settings)

    assert claims["iss"] == "devkey"
    assert claims["sub"] == "me"
    assert claims["video"]["room"] == "r"
    assert claims["video"]["roomJoin"] is True
    assert claims["roomConfig"]["agents"] == [{"agentName": "smoke"}]


def test_make_token_without_agent_has_no_dispatch(voice_settings: VoiceSettings) -> None:
    claims = _decode(make_token(voice_settings, "r", "me"), voice_settings)

    assert claims["video"]["room"] == "r"
    assert "roomConfig" not in claims


def test_make_token_rejects_an_empty_room(voice_settings: VoiceSettings) -> None:
    with pytest.raises(ValueError, match="room"):
        make_token(voice_settings, "", "me")
