import json
import math
from pathlib import Path

from livekit.agents import llm

from tests.fakes import FakeChatStream, FakeLlm, FakeStt, FakeTts
from voice_arch.bench_runs import LlmCase, load_llm_cases, run_llm, run_stt, run_tts
from voice_arch.corpus import Utterance, build_corpus
from voice_arch.winners import LlmRow

LLM_CASES_FILE = Path(__file__).resolve().parents[1] / "data" / "llm_cases.jsonl"
_UTTERANCES = [
    Utterance("u1", "My name is John Miller.", {"name": "John Miller"}),
    Utterance("u2", "Call me on 415 555 0134.", {"phone": "4155550134"}),
]


async def test_run_stt_counts_field_errors_per_candidate(tmp_path: Path) -> None:
    corpus = await build_corpus(_UTTERANCES, FakeTts(), tmp_path, tts_model="m", voice="v")
    stts = {
        "good": FakeStt(delay_s=0.02),
        "wrong_phone": FakeStt(hear=lambda spoken: spoken.replace("0134", "0135")),
        "empty": FakeStt(hear=lambda spoken: ""),
    }

    rows = {row.model: row for row in await run_stt(stts, corpus, _UTTERANCES)}

    assert (rows["good"].errors, rows["good"].n_utterances) == (0, 2)
    assert rows["good"].p50_s >= 0.02
    assert rows["wrong_phone"].errors == 1
    assert rows["empty"].errors == 2  # F-10: an empty transcript errs on every field


async def test_run_tts_measures_first_frame_and_round_trip_intelligibility() -> None:
    lines = ["Hello there friend.", "Tuesday morning works."]
    ttss = {"a": FakeTts(first_delay_s=0.03), "b": FakeTts(say=lambda text: "zzz qqq")}
    judge = FakeStt()

    rows = {row.model: row for row in await run_tts(ttss, lines, judge, reps=2)}

    assert rows["a"].intelligible is True
    assert 0.03 <= rows["a"].ttfb_p50_s < 1.0
    assert rows["b"].intelligible is False
    assert ttss["a"].calls == [line for line in lines for _ in range(2)]
    assert judge.calls == 4  # one judge call per line and candidate, not per rep


def _answer(caller: str) -> tuple[str, str] | None:
    if "John" in caller:
        return "record_name", json.dumps({"name": "John Miller"})
    if "number" in caller:
        return "record_phone", json.dumps({"phone": "(415) 555-0134"})
    return None


_CASES = [
    LlmCase("n01", "My name is John Miller.", "record_name", {"name": "John Miller"}),
    LlmCase("p01", "My number is 415 555 0134.", "record_phone", {"phone": "4155550134"}),
    LlmCase("g01", "The sink leaks.", "record_problem", {"problem_type": "plumbing"}),
]


async def test_run_llm_scores_tool_and_normalised_args() -> None:
    llms = {
        "good": FakeLlm(_answer, first_delay_s=0.02),
        "wrong_tool": FakeLlm(lambda caller: ("record_phone", json.dumps({"phone": "1"}))),
        "no_tool": FakeLlm(lambda caller: None),
        "bad_json": FakeLlm(lambda caller: ("record_name", "{not json")),
    }

    rows = {row.model: row for row in await run_llm(llms, _CASES)}

    assert rows["good"] == LlmRow("good", correct=2, n_cases=3, ttft_p50_s=rows["good"].ttft_p50_s)
    assert rows["good"].ttft_p50_s >= 0.02
    assert [rows[m].correct for m in ("wrong_tool", "no_tool", "bad_json")] == [0, 0, 0]


def test_load_llm_cases_reads_the_shipped_cases() -> None:
    cases = load_llm_cases(LLM_CASES_FILE)

    assert len(cases) == 20
    assert cases[0] == LlmCase("n01", "My name is John Miller.", "record_name", {"name": "John Miller"})


async def test_run_llm_rejects_right_args_under_the_wrong_tool_name() -> None:
    llms = {"m": FakeLlm(lambda caller: ("record_address", json.dumps({"name": "John Miller"})))}

    (row,) = await run_llm(llms, _CASES[:1])

    assert row.correct == 0


async def test_empty_tts_stream_marks_candidate_unintelligible() -> None:
    ttss = {"mute": FakeTts(silent=True), "ok": FakeTts(first_delay_s=0.01)}

    rows = {row.model: row for row in await run_tts(ttss, ["Hello there friend."], FakeStt(), reps=2)}

    assert rows["mute"].intelligible is False
    assert rows["mute"].ttfb_p50_s == math.inf
    assert rows["ok"].intelligible is True
    assert 0.01 <= rows["ok"].ttfb_p50_s < 1.0


class _EmptyLlm:
    model = "fake/empty"

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None) -> FakeChatStream:
        return FakeChatStream([], 0.0)


class _FirstCaseEmptyLlm(FakeLlm):
    """Answers every case correctly, but the first stream yields no chunk."""

    def chat(self, *, chat_ctx: llm.ChatContext, tools: list[llm.Tool] | None = None) -> FakeChatStream:
        stream = super().chat(chat_ctx=chat_ctx, tools=tools)
        return FakeChatStream([], 0.0) if self.calls == 1 else stream


async def test_llm_case_with_no_chunk_is_incorrect_and_excluded_from_ttft() -> None:
    llms = {"empty": _EmptyLlm(), "partial": _FirstCaseEmptyLlm(_answer, first_delay_s=0.02)}

    rows = {row.model: row for row in await run_llm(llms, _CASES[:2])}

    assert (rows["empty"].correct, rows["empty"].ttft_p50_s) == (0, math.inf)
    assert rows["partial"].correct == 1  # the case with no chunk is incorrect
    assert 0.02 <= rows["partial"].ttft_p50_s < 1.0  # median of the one measured case, not pulled to 0
