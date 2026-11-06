"""Live OpenRouter (D-4): do the LiveKit openai plugins work against it? Costs a few cents per run."""

from pathlib import Path

import pytest

from datalab.project import repo_root
from voice_arch.audio import make_llm, make_stt, make_tts
from voice_arch.bench_runs import load_llm_cases, read_wav, run_llm
from voice_arch.candidates import CORPUS_TTS_MODEL, CORPUS_VOICE
from voice_arch.corpus import build_corpus, load_utterances
from voice_arch.fields import field_errors
from voice_arch.settings import VoiceSettings

pytestmark = pytest.mark.integration

PROJECT_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def live() -> VoiceSettings:
    return VoiceSettings(_env_file=(repo_root() / ".env", PROJECT_DIR / ".env"))  # pyright: ignore[reportCallIssue]


async def test_openrouter_stt_returns_text(live: VoiceSettings, tmp_path: Path) -> None:
    utterance = load_utterances(PROJECT_DIR / "data" / "utterances.jsonl")[0]
    corpus_tts = make_tts(live, CORPUS_TTS_MODEL, CORPUS_VOICE)
    corpus = await build_corpus([utterance], corpus_tts, tmp_path, tts_model=CORPUS_TTS_MODEL, voice=CORPUS_VOICE)

    event = await make_stt(live).recognize(read_wav(corpus.paths[utterance.id]))

    text = event.alternatives[0].text
    assert text.strip()  # F-10: a non-empty body
    assert field_errors(text, {"name": utterance.truth["name"]}) == {"name": False}


async def test_openrouter_tts_returns_frames(live: VoiceSettings) -> None:
    frames = [event.frame async for event in make_tts(live).synthesize("Hello")]

    assert len(frames) >= 1


async def test_openrouter_llm_calls_a_tool(live: VoiceSettings) -> None:
    case = load_llm_cases(PROJECT_DIR / "data" / "llm_cases.jsonl")[0]

    (row,) = await run_llm({live.llm_model: make_llm(live)}, [case])

    assert (row.correct, row.n_cases) == (1, 1)
