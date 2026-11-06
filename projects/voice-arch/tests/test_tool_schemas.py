import json
from pathlib import Path

from livekit.agents import llm

from voice_arch.tool_schemas import TOOL_SCHEMAS, to_openai_tools, to_raw_tools

LLM_CASES_FILE = Path(__file__).resolve().parents[1] / "data" / "llm_cases.jsonl"


def test_u_26_llm_cases_match_tool_schemas() -> None:
    args_by_tool = {schema.name: {arg.name for arg in schema.args} for schema in TOOL_SCHEMAS}
    cases = [json.loads(line) for line in LLM_CASES_FILE.read_text().splitlines() if line.strip()]

    assert len(cases) == 20
    for case in cases:
        assert case["expected_tool"] in args_by_tool, case["id"]
        assert set(case["expected_args"]) == args_by_tool[case["expected_tool"]], case["id"]


def test_tool_names_are_the_five_booking_tools() -> None:
    assert [s.name for s in TOOL_SCHEMAS] == [
        "record_name",
        "record_phone",
        "record_address",
        "record_problem",
        "choose_slot",
    ]


def test_openai_tools_are_flat_dicts_with_enum_for_problem_type() -> None:
    tools = {t["name"]: t for t in to_openai_tools()}

    problem = tools["record_problem"]["parameters"]["properties"]["problem_type"]
    assert problem["enum"] == ["plumbing", "electrical", "hvac", "appliance", "other"]
    assert tools["record_name"]["parameters"]["required"] == ["name"]
    assert "function" not in tools["record_name"]


def test_raw_tools_are_livekit_tool_objects() -> None:
    raw = to_raw_tools()

    assert [t.info.name for t in raw] == [s.name for s in TOOL_SCHEMAS]
    assert all(isinstance(t, llm.RawFunctionTool) for t in raw)
