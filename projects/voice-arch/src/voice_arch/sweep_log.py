"""What a sweep writes: the JSONL rows and the MLflow params (D-9). The metrics come from `scoring.aggregate`."""

import json
from collections.abc import Sequence
from pathlib import Path

from voice_arch.arch import Arch
from voice_arch.call import CallRow
from voice_arch.personas import Persona
from voice_arch.scoring import FULL_REPS
from voice_arch.settings import VoiceSettings
from voice_arch.worker_logic import TURN_HANDLING


def append_row(path: Path, row: CallRow) -> None:
    """Written at once, so a sweep that dies later still leaves its finished calls behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(row.model_dump_json() + "\n")


def static_params(arch: Arch, personas: Sequence[Persona], reps: int, s: VoiceSettings) -> dict[str, str | float]:
    """Known before the first call. Neither the worker (ESC-2-1) nor the caller pins an OpenRouter provider."""
    return {
        "arch": arch.value, "stt_model": s.stt_model, "tts_model": s.tts_model, "tts_voice": s.tts_voice,
        "llm_model": s.llm_model, "caller_llm_model": s.caller_llm_model, "caller_temperature": s.caller_temperature,
        "llm_providers": "none", "reps": reps, "personas": ",".join(p.id for p in personas),
        "full_reps": FULL_REPS, "call_timeout_s": s.call_timeout_s, "agent_join_timeout_s": s.agent_join_timeout_s,
        "turn_handling": json.dumps(TURN_HANDLING, sort_keys=True),
    }  # fmt: skip


def worker_params(rows: Sequence[CallRow]) -> dict[str, str]:
    """What the worker itself reported in its first result (empty when no call produced one)."""
    reported = next((r for r in rows if r.max_tool_steps is not None), None)
    if reported is None:
        return {}
    summarize = "n/a" if reported.summarize_chat_ctx is None else str(reported.summarize_chat_ctx)  # A: no TaskGroup
    return {"max_tool_steps": str(reported.max_tool_steps), "summarize_chat_ctx": summarize}
