import json
from pathlib import Path

import pytest

from tests.fakes import FakeTts
from voice_arch.corpus import Utterance, build_corpus, load_utterances

UTTERANCES_FILE = Path(__file__).resolve().parents[1] / "data" / "utterances.jsonl"
_UTTERANCES = [
    Utterance("u1", "My name is John Miller.", {"name": "John Miller"}),
    Utterance("u2", "Call me on 415 555 0134.", {"phone": "4155550134"}),
]


async def _build(tts: FakeTts, out_dir: Path, voice: str = "v1", utterances: list[Utterance] = _UTTERANCES):
    return await build_corpus(utterances, tts, out_dir, tts_model="m", voice=voice)


async def test_build_corpus_writes_one_wav_per_utterance(tmp_path: Path) -> None:
    corpus = await _build(FakeTts(), tmp_path)

    assert sorted(corpus.paths) == ["u1", "u2"]
    assert all(path.read_bytes().startswith(b"RIFF") for path in corpus.paths.values())
    assert not list(tmp_path.glob("*.tmp"))


async def test_valid_cache_is_reused_without_synthesis(tmp_path: Path) -> None:
    first = await _build(FakeTts(), tmp_path)
    again = FakeTts()

    second = await _build(again, tmp_path)

    assert again.calls == []
    assert second.hash == first.hash


async def test_f_11_truncated_or_other_voice_cache_is_rejected(tmp_path: Path) -> None:
    first = await _build(FakeTts(), tmp_path)

    truncated = FakeTts()
    first.paths["u2"].write_bytes(first.paths["u2"].read_bytes()[:20])
    await _build(truncated, tmp_path)
    other_voice = FakeTts()
    changed = await _build(other_voice, tmp_path, voice="v2")

    assert truncated.calls == [u.text for u in _UTTERANCES]
    assert other_voice.calls == [u.text for u in _UTTERANCES]
    assert changed.hash != first.hash


async def test_cache_is_rejected_when_an_utterance_text_changed(tmp_path: Path) -> None:
    await _build(FakeTts(), tmp_path)
    edited = [_UTTERANCES[0], Utterance("u2", "Call me on 415 555 0199.", {"phone": "4155550199"})]
    tts = FakeTts()

    await _build(tts, tmp_path, utterances=edited)

    assert tts.calls == [u.text for u in edited]


async def test_corrupt_manifest_is_rejected_and_rebuilt(tmp_path: Path) -> None:
    await _build(FakeTts(), tmp_path)
    (tmp_path / "manifest.json").write_text("{not json")
    tts = FakeTts()

    corpus = await _build(tts, tmp_path)

    assert len(tts.calls) == 2
    assert json.loads((tmp_path / "manifest.json").read_text())["voice"] == "v1"
    assert len(corpus.hash) == 64


def _write(path: Path, row: dict[str, object]) -> Path:
    path.write_text(json.dumps(row) + "\n")
    return path


def test_utterance_truth_must_appear_in_text(tmp_path: Path) -> None:
    bad = _write(tmp_path / "u.jsonl", {"id": "u9", "text": "Hello there.", "truth": {"phone": "4155550134"}})

    with pytest.raises(ValueError, match="u9"):
        load_utterances(bad)


def test_load_utterances_reads_the_shipped_corpus() -> None:
    utterances = load_utterances(UTTERANCES_FILE)

    assert len(utterances) == 40
    assert len({u.id for u in utterances}) == 40
    assert all(u.truth for u in utterances)


def test_load_utterances_rejects_duplicate_ids(tmp_path: Path) -> None:
    row = {"id": "u1", "text": "I am John Miller.", "truth": {"name": "John Miller"}}
    path = tmp_path / "u.jsonl"
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="duplicate"):
        load_utterances(path)
