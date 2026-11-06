"""Stage-1 candidates (plan section 4): models are OpenRouter ids; a TTS candidate is (model, voice)."""

from typing import Final

STT_CANDIDATES: Final = ("deepgram/nova-3", "assemblyai/universal-3-6-pro", "openai/gpt-4o-mini-transcribe")
TTS_CANDIDATES: Final = (
    ("elevenlabs/eleven-flash-v2.5", "21m00Tcm4TlvDq8ikWAM"),
    ("deepgram/aura-2", "aura-2-thalia-en"),
    ("deepgram/flux-tts", "flux-bree-en"),
)
LLM_CANDIDATES: Final = ("deepseek/deepseek-v4-flash", "google/gemini-3.5-flash-lite", "anthropic/claude-haiku-5.5")

# The corpus voice comes from a vendor that is not an STT candidate, so no STT is favoured.
CORPUS_TTS_MODEL: Final = "google/gemini-3.8-flash-lite-tts"
CORPUS_VOICE: Final = "Kore"
