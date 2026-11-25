from livekit.agents import llm

from voice_arch.agents.arch_a import OrchestratorAgent
from voice_arch.agents.arch_b import (
    SUMMARIZE_CHAT_CTX,
    AddressTask,
    ConfirmTask,
    NameTask,
    PhoneTask,
    ProblemTask,
    SlotTask,
    build_task_group,
    ends_with_user_turn,
)
from voice_arch.agents.arch_c import build_task_group_c
from voice_arch.agents.registry import build_agent
from voice_arch.arch import Arch
from voice_arch.booking import instructions as text

STEP_IDS = ["name", "phone", "address", "problem", "slot", "confirm"]


async def test_f_15_taskgroup_summarize_flag_is_off_and_logged() -> None:
    group = build_task_group()

    assert SUMMARIZE_CHAT_CTX is False
    assert group._summarize_chat_ctx is False  # pyright: ignore[reportPrivateUsage]  # test reads private attr


async def test_task_group_has_the_six_steps_in_order() -> None:
    group = build_task_group()

    assert list(group._registered_factories) == STEP_IDS  # pyright: ignore[reportPrivateUsage]  # private attr


async def test_task_group_factories_make_fresh_tasks_of_the_right_class() -> None:
    factories = build_task_group()._registered_factories  # pyright: ignore[reportPrivateUsage]  # private attr
    classes = [NameTask, PhoneTask, AddressTask, ProblemTask, SlotTask, ConfirmTask]

    made = [factories[step].task_factory() for step in STEP_IDS]

    assert [type(task) for task in made] == classes
    assert made[0] is not factories["name"].task_factory()


async def test_each_task_completes_on_its_own_field() -> None:
    fields = [cls.FIELD for cls in (NameTask, PhoneTask, AddressTask, ProblemTask, SlotTask, ConfirmTask)]

    assert fields == ["name", "phone", "address", "problem_type", "slot_id", "confirmed"]


async def test_task_instructions_carry_the_shared_context_and_its_own_ask() -> None:
    task = PhoneTask()

    assert text.CONTEXT in str(task.instructions)
    assert text.ASK_PHONE in str(task.instructions)
    assert text.ASK_NAME not in str(task.instructions)


async def test_slot_task_has_check_and_choose_tools_only() -> None:
    names = {tool.info.name for tool in SlotTask().tools}  # pyright: ignore[reportAttributeAccessIssue]  # not in stubs

    assert names == {"check_slots", "choose_slot"}


async def test_arch_c_tasks_add_the_record_tools_and_keep_the_same_steps() -> None:
    group = build_task_group_c()
    task = group._registered_factories["phone"].task_factory()  # pyright: ignore[reportPrivateUsage]  # private attr
    names = {tool.info.name for tool in task.tools}  # pyright: ignore[reportAttributeAccessIssue]  # not in stubs

    assert list(group._registered_factories) == STEP_IDS  # pyright: ignore[reportPrivateUsage]  # private attr
    assert names == {"record_phone", "read_record", "update_record"}


async def test_orchestrator_carries_every_instruction_and_all_tools() -> None:
    agent = OrchestratorAgent()
    body = str(agent.instructions)

    for part in (text.CONTEXT, text.GREETING, text.ASK_NAME, text.ASK_PHONE, text.ASK_ADDRESS, text.ASK_PROBLEM):
        assert part in body
    assert {t.info.name for t in agent.tools} == {  # pyright: ignore[reportAttributeAccessIssue]  # not in stubs
        "record_name",
        "record_phone",
        "record_address",
        "record_problem",
        "check_slots",
        "choose_slot",
        "confirm_booking",
    }


async def test_registry_builds_the_agent_for_each_arch() -> None:
    kinds = {arch: type(build_agent(arch)).__name__ for arch in Arch}

    assert kinds == {Arch.A: "OrchestratorAgent", Arch.B: "BookingFlowAgent", Arch.C: "BookingFlowAgent"}


def _ctx_of(*roles: str) -> llm.ChatContext:
    ctx = llm.ChatContext.empty()
    for role in roles:
        # Loose test fake.
        ctx.add_message(role=role, content=[f"{role} said something"])  # pyright: ignore[reportArgumentType]  # role is a plain str here; LiveKit types it as a Literal
    return ctx


def test_ends_with_user_turn_adds_a_stand_in_after_an_assistant_message() -> None:
    original = _ctx_of("user", "assistant")

    fixed = ends_with_user_turn(original)

    last = fixed.items[-1]
    assert isinstance(last, llm.ChatMessage)
    assert (last.role, last.text_content) == ("user", text.CALLER_WAITING)
    assert len(original.items) == 2  # the agent's own context is never touched


def test_ends_with_user_turn_leaves_a_user_ending_context_alone() -> None:
    fixed = ends_with_user_turn(_ctx_of("assistant", "user"))

    assert [i.role for i in fixed.items if isinstance(i, llm.ChatMessage)] == ["assistant", "user"]


def test_ends_with_user_turn_handles_an_empty_context() -> None:
    fixed = ends_with_user_turn(llm.ChatContext.empty())

    assert [i.role for i in fixed.items if isinstance(i, llm.ChatMessage)] == ["user"]
