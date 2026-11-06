"""The stage-1 audio corpus: caller utterances synthesised once and cached with a verified manifest (F-11)."""

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livekit import rtc

from voice_arch.fields import field_errors
from voice_arch.seams import Synthesizer

MANIFEST = "manifest.json"


class EmptyAudioError(Exception):
    """A TTS stream ended without yielding any audio."""


@dataclass(frozen=True)
class Utterance:
    id: str
    text: str
    truth: Mapping[str, str]


@dataclass(frozen=True)
class Corpus:
    paths: dict[str, Path]
    hash: str


def load_utterances(path: Path) -> list[Utterance]:
    """Every truth value must appear in its text under the field's normaliser, else the bench would score noise."""
    utterances: list[Utterance] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        utterance = Utterance(row["id"], row["text"], row["truth"])
        if any(u.id == utterance.id for u in utterances):
            raise ValueError(f"{path}: duplicate utterance id {utterance.id!r}")
        missing = sorted(k for k, wrong in field_errors(utterance.text, utterance.truth).items() if wrong)
        if missing:
            raise ValueError(f"utterance {utterance.id!r}: truth {missing} does not appear in its text")
        utterances.append(utterance)
    return utterances


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wanted(utterances: list[Utterance], tts_model: str, voice: str, shas: Mapping[str, str]) -> dict[str, object]:
    files = {u.id: {"text_sha256": _sha256(u.text.encode()), "wav_sha256": shas.get(u.id, "")} for u in utterances}
    return {"tts_model": tts_model, "voice": voice, "files": files}


def _cached(manifest: Path, out_dir: Path, utterances: list[Utterance], tts_model: str, voice: str) -> bool:
    """True only when the manifest lists the same ids, texts, model and voice and every wav's hash matches."""
    try:
        stored = json.loads(manifest.read_text(encoding="utf-8"))
        shas = {u.id: _sha256((out_dir / f"{u.id}.wav").read_bytes()) for u in utterances}
    except (OSError, ValueError):
        return False
    return stored == _wanted(utterances, tts_model, voice, shas)


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


async def build_corpus(
    utterances: list[Utterance], tts: Synthesizer, out_dir: Path, *, tts_model: str, voice: str
) -> Corpus:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / MANIFEST
    if not _cached(manifest, out_dir, utterances, tts_model, voice):
        for utterance in utterances:
            frames = [event.frame async for event in tts.synthesize(utterance.text)]
            if not frames:
                raise EmptyAudioError(f"{tts.model}: TTS returned no audio")
            frame = rtc.combine_audio_frames(frames)
            _atomic_write(out_dir / f"{utterance.id}.wav", frame.to_wav_bytes())
        shas = {u.id: _sha256((out_dir / f"{u.id}.wav").read_bytes()) for u in utterances}
        body = json.dumps(_wanted(utterances, tts_model, voice, shas), sort_keys=True, indent=1)
        _atomic_write(manifest, body.encode("utf-8"))
    paths = {u.id: out_dir / f"{u.id}.wav" for u in utterances}
    return Corpus(paths, _sha256(manifest.read_bytes()))
