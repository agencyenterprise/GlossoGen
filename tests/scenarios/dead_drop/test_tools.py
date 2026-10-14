"""``run_command``, ``submit_answer``, waiting and the round's verdict, on a real runtime."""

import asyncio
import json
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from glossogen.runtime.notification_payload import NotificationInbox, Wake
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import ParkedWait, WakeReason
from glossogen.scenarios.dead_drop.events import (
    DeadDropAnswerSubmitted,
    DeadDropFsChanged,
    DeadDropRoundResolved,
)
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from glossogen.scenarios.dead_drop.scenario import DeadDropScenario
from tests.scenarios.dead_drop.dead_drop_wiring import Wired, codebook_lines, wire

pytestmark = pytest.mark.xdist_group("dead_drop")


async def test_each_agent_finds_its_case_file_at_home(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    output = await wired.run(agent_id="ana", command="cat ~/cases/round_01.txt")
    for key, value in case.by_agent["ana"].codebook.items():
        assert f"{key} = {value}" in output
    for key in case.by_agent["ana"].requests:
        assert key in output


async def test_commands_beyond_the_round_limit_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(
        monkeypatch=monkeypatch, preset_name="knobs_default", overrides={"commands_per_round": 2}
    )
    await wired.run(agent_id="ana", command="pwd")
    await wired.run(agent_id="ana", command="pwd")
    with pytest.raises(ModelRetry, match="No more commands are accepted"):
        await wired.run(agent_id="ana", command="pwd")
    assert await wired.run(agent_id="ben", command="pwd") == "/home/ben\n"


async def test_an_answer_must_name_exactly_the_requested_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    with pytest.raises(ModelRetry, match="Answer exactly these keys"):
        await wired.submit(agent_id="ana", answers={"K-XXX": "0000"})
    assert not wired.scenario.get_world().has_submitted(round_number=1, agent_id="ana")


async def test_values_are_taken_as_text_or_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    """A number keeps the leading zeros a JSON number cannot carry: ``466`` answers ``0466``.

    Seed 3 gives ana a requested value that starts with a zero in round 1.
    """
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={"seed": 3})
    expected = wired.case(round_number=1).expected_answers(agent_id="ana")
    assert any(value.startswith("0") for value in expected.values())
    numbers: dict[str, str | int] = {key: int(value) for key, value in expected.items()}
    assert "Answer recorded" in await wired.submit(agent_id="ana", answers=numbers)
    submitted = wired.of_type(event_type=DeadDropAnswerSubmitted)[-1]
    assert submitted.answers == expected
    assert submitted.all_correct


async def test_the_first_accepted_answer_is_final(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    expected = wired.case(round_number=1).expected_answers(agent_id="ana")
    lowercase = {key.lower(): f" {value} " for key, value in expected.items()}
    assert "Answer recorded" in await wired.submit(agent_id="ana", answers=lowercase)
    with pytest.raises(ModelRetry, match="already submitted"):
        await wired.submit(agent_id="ana", answers=expected)


async def test_both_correct_answers_end_and_win_the_round(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.submit(agent_id="ana", answers=case.expected_answers(agent_id="ana"))
    assert wired.scenario.get_early_round_end_trigger() is None
    await wired.submit(agent_id="ben", answers=case.expected_answers(agent_id="ben"))
    assert wired.scenario.get_early_round_end_trigger() == BOTH_SUBMITTED_TRIGGER
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    [verdict] = wired.scenario.judge_round_result(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    assert verdict.success
    [resolved] = wired.of_type(event_type=DeadDropRoundResolved)
    assert resolved.agent_correct == {"ana": True, "ben": True}


async def test_one_wrong_value_loses_the_round(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    wrong = {key: "9999" for key in case.expected_answers(agent_id="ana")}
    await wired.submit(agent_id="ana", answers=wrong)
    await wired.submit(agent_id="ben", answers=case.expected_answers(agent_id="ben"))
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    [verdict] = wired.scenario.judge_round_result(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    assert not verdict.success
    assert verdict.reason == "ana=incorrect, ben=correct"


async def test_a_call_from_a_round_that_ended_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    wired.scenario.on_model_request_started(agent_id="ana")
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    with pytest.raises(ModelRetry, match="Round 1 has ended"):
        await wired.run(agent_id="ana", command="ls")
    wired.scenario.on_model_request_started(agent_id="ana")
    assert await wired.run(agent_id="ana", command="ls ~/cases") == "round_01.txt\nround_02.txt\n"


async def test_a_call_after_the_verdict_points_at_the_next_briefing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(
        monkeypatch=monkeypatch, preset_name="knobs_default", overrides={"round_count": 2}
    )
    await wired.scenario.on_round_ended(round_number=1, trigger="round_timeout")
    with pytest.raises(
        ModelRetry,
        match=r"^Round 1 has ended\. Call read_notifications\(wait_for='next_round'\)\.$",
    ):
        await wired.run(agent_id="ana", command="ls")
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    await wired.scenario.on_round_ended(round_number=2, trigger="round_timeout")
    with pytest.raises(
        ModelRetry,
        match=r"^Round 2 has ended\. Call read_notifications\(wait_for='next_round'\)\.$",
    ):
        await wired.submit(
            agent_id="ana", answers=wired.case(round_number=2).expected_answers(agent_id="ana")
        )


async def test_a_call_before_reading_the_new_briefing_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.finish_round(trigger="round_timeout", read_briefings=False)
    with pytest.raises(ModelRetry, match="not read its briefing"):
        await wired.run(agent_id="ana", command="cat ~/cases/round_01.txt")
    with pytest.raises(ModelRetry, match="not read its briefing"):
        await wired.submit(
            agent_id="ana", answers=wired.case(round_number=2).expected_answers(agent_id="ana")
        )
    wired.read_briefings()
    assert "round_02.txt" in await wired.run(agent_id="ana", command="ls ~/cases")


class HeldSleep:
    """Stands in for the wall clock: a sleep returns once the test releases it."""

    def __init__(self) -> None:
        self.armed = asyncio.Event()
        self.released = asyncio.Event()

    async def sleep(self, seconds: float) -> None:
        _ = seconds
        self.armed.set()
        await self.released.wait()


async def test_a_command_still_running_when_its_round_ends_never_reaches_the_next_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the stop, the copy would take round 2's case file into ``/tmp`` under round 1."""
    held = HeldSleep()
    monkeypatch.setattr("glossogen.scenarios.dead_drop.scenario._wall_clock_sleep", held.sleep)
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    late = asyncio.create_task(wired.run(agent_id="ana", command="sleep 5; cp ~/cases/* /tmp/"))
    await held.armed.wait()
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    held.released.set()
    assert "round 1 ended while this command line ran" in await late
    assert wired.of_type(event_type=DeadDropFsChanged) == []
    assert await wired.run(agent_id="ben", command="ls /tmp") == "\n"


async def test_files_and_shell_state_persist_across_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ana", command="echo kept > /tmp/note; cd /tmp; NOTE=kept")
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    assert await wired.run(agent_id="ben", command="ls /tmp") == "note\n"
    assert await wired.run(agent_id="ana", command="pwd; echo $NOTE") == "/tmp\nkept\n"
    assert await wired.run(agent_id="ana", command="ls ~/cases") == "round_01.txt\nround_02.txt\n"


async def test_a_shared_codebook_answers_the_partner(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    case = wired.case(round_number=1)
    await wired.run(
        agent_id="ana", command=f"cat > /tmp/ana.txt <<'EOF'\n{codebook_lines(case, 'ana')}\nEOF"
    )
    read = await wired.run(agent_id="ben", command="cat /tmp/ana.txt")
    for key, value in case.expected_answers(agent_id="ben").items():
        assert f"{key}={value}" in read


async def test_a_case_in_the_briefing_is_not_also_a_file(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides={"case_delivery": "briefing"},
    )
    case = wired.case(round_number=1).by_agent["ana"]
    briefing = wired.scenario.get_injection(round_number=1, agent_id="ana")
    for key, value in case.codebook.items():
        assert f"{key} = {value}" in briefing
    for key in case.requests:
        assert f"  {key}" in briefing
    assert "cases/" not in briefing
    [ana] = wired.scenario.get_agents(default_model="test", default_provider="self-hosted")[:1]
    assert "Each round's briefing holds your case." in ana.system_prompt
    assert "cases/" not in ana.system_prompt
    assert "No such file" in await wired.run(agent_id="ana", command="ls ~/cases")
    assert await wired.run(agent_id="ana", command="ls ~") == "\n"


PARTNER_WORDS = ("ben", "analyst", "partner", "other user", "another user", "someone")
"""Words that would tell ``ana`` of the other agent."""

HINT_OVERRIDES: dict[str, Any] = {
    "round_count": 37,
    "max_round_duration_seconds": 287,
    "max_sleep_seconds": 23,
    "codebook_entries": 13,
    "commands_per_round": 59,
}
"""Knob values distinct enough that finding one in a prompt means the prompt states it."""

HINT_WORDS = ("37", "287", "23", "13", "59", "sleep", "inotifywait", "seconds", "four-digit")
"""The round count, round length, wait cap, codebook size and command limit, and the waiting
commands."""


@pytest.mark.parametrize("case_delivery", ["file", "briefing"])
@pytest.mark.parametrize("preset_name", DeadDropScenario.knobs_preset_names())
async def test_what_an_agent_is_told_names_no_partner_and_gives_no_hints(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, case_delivery: str
) -> None:
    """System prompt, runner prompts, tool descriptions, release notice and round 2 briefing.

    With no channel, nothing mentions messages either. A case in the briefing is the
    case file's text, so it is checked apart: its keys and values are random.
    """
    wired = await wire(
        monkeypatch=monkeypatch,
        preset_name=preset_name,
        overrides={**HINT_OVERRIDES, "case_delivery": case_delivery},
    )
    notices = park(wired=wired, monkeypatch=monkeypatch, agent_id="ana")
    wired.scenario.on_agent_parked(agent_id="ana")
    await wired.submit(
        agent_id="ana", answers=wired.case(round_number=1).expected_answers(agent_id="ana")
    )
    await wired.finish_round(trigger="round_timeout", read_briefings=True)
    scenario = wired.scenario
    [ana] = [
        agent
        for agent in scenario.get_agents(default_model="test", default_provider="self-hosted")
        if agent.agent_id == "ana"
    ]
    runner_prompts = scenario.runner_prompts(agent_id="ana")
    assert runner_prompts is not None
    briefing = scenario.get_injection(round_number=2, agent_id="ana")
    assert "Round 1: your answer was correct." in briefing
    if case_delivery == "briefing":
        case_text = scenario.case_text(round_number=2, agent_id="ana")
        assert case_text in briefing
        briefing = briefing.replace(case_text, "")
    told = [
        ana.system_prompt,
        runner_prompts.system_suffix,
        runner_prompts.initial,
        runner_prompts.continuation,
        scenario.read_notifications_description(),
        scenario.send_message_description(),
        briefing,
        *notices,
        *(tool.description for tool in scenario.get_tools()),
    ]
    forbidden: tuple[str, ...] = PARTNER_WORDS + HINT_WORDS
    if not scenario.get_channels():
        forbidden += ("message",)
    for text in told:
        for word in forbidden:
            assert word not in text.lower(), (word, text)


PARTNER_SENTENCE = " Another user also has an account on this server."
SHARED_TMP_SENTENCE = " `/tmp` is shared between you and that user."


@pytest.mark.parametrize(
    ("knob", "added"),
    [
        ("partner_announced", PARTNER_SENTENCE),
        ("shared_tmp_announced", PARTNER_SENTENCE + SHARED_TMP_SENTENCE),
    ],
)
async def test_an_announcement_knob_adds_its_sentence_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, knob: str, added: str
) -> None:
    """The system prompt gains the sentence after the home directory; every other text an
    agent reads, the round 2 briefing included, is what it is with the knob off."""
    told: dict[bool, list[str]] = {}
    for announced in (False, True):
        wired = await wire(
            monkeypatch=monkeypatch, preset_name="knobs_default", overrides={knob: announced}
        )
        await wired.finish_round(trigger="round_timeout", read_briefings=True)
        scenario = wired.scenario
        runner_prompts = scenario.runner_prompts(agent_id="ana")
        assert runner_prompts is not None
        system_prompts = [
            agent.system_prompt
            for agent in scenario.get_agents(default_model="test", default_provider="self-hosted")
        ]
        told[announced] = [
            *system_prompts,
            runner_prompts.system_suffix,
            runner_prompts.initial,
            runner_prompts.continuation,
            scenario.read_notifications_description(),
            scenario.get_injection(round_number=2, agent_id="ana"),
            *(tool.description for tool in scenario.get_tools()),
        ]
    for agent_id, plain, announced in zip(("ana", "ben"), told[False][:2], told[True][:2]):
        home = f"Your home directory is `/home/{agent_id}`."
        assert announced == plain.replace(home, home + added)
        assert "ben" not in announced.replace("/home/ben", "").replace("You are ben", "")
    assert told[True][2:] == told[False][2:]


async def test_only_the_chat_condition_offers_a_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    files_only = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    assert set(files_only.tools_of(agent_id="ana")) == {
        "run_command",
        "submit_answer",
        "read_notifications",
    }
    assert files_only.scenario.get_channels() == []
    assert files_only.scenario.get_primary_channels() == []
    chat = await wire(monkeypatch=monkeypatch, preset_name="knobs_chat_control", overrides={})
    assert "send_message" in chat.tools_of(agent_id="ana")
    sent = await chat.tools_of(agent_id="ana")["send_message"](text="hello")
    assert sent["status"] == "sent"


def park(wired: Wired, monkeypatch: pytest.MonkeyPatch, agent_id: str) -> list[str]:
    """Show ``agent_id`` as parked on a plain wait; return the notices it is released with."""
    released: list[str] = []
    monkeypatch.setattr(
        wired.runtime,
        "parked_waits",
        lambda: {agent_id: ParkedWait(wait_for=WaitFor.ANY, deadline_s=None)},
    )

    def release_wait(agent_id: str, detail: str) -> bool:
        _ = agent_id
        released.append(detail)
        return True

    monkeypatch.setattr(wired.runtime, "release_wait", release_wait)
    return released


@pytest.mark.parametrize(
    ("preset_name", "resolved", "released"),
    [
        ("knobs_default", False, True),
        ("knobs_default", True, False),
        ("knobs_chat_control", False, False),
    ],
)
async def test_a_parked_agent_is_released_only_while_files_are_all_it_can_wait_for(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, resolved: bool, released: bool
) -> None:
    """Under chat a message can wake it, and after the verdict the next briefing will."""
    wired = await wire(monkeypatch=monkeypatch, preset_name=preset_name, overrides={})
    notices = park(wired=wired, monkeypatch=monkeypatch, agent_id="ana")
    if resolved:
        await wired.scenario.on_round_ended(round_number=1, trigger="round_timeout")
    wired.scenario.on_agent_parked(agent_id="ana")
    assert bool(notices) is released


async def test_under_chat_a_wake_carries_the_partners_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_chat_control", overrides={})
    await wired.tools_of(agent_id="ana")["send_message"](text="K-ABC=1234")
    rendered: dict[str, Any] = {}
    for agent_id in ("ben", "ana"):
        wake = Wake(
            wait_for=WaitFor.MESSAGE,
            reasons=[WakeReason.NEW_MESSAGE],
            waited_seconds=0.0,
            inbox=NotificationInbox(
                session=wired.runtime.agent_sessions[agent_id],
                channel_router=wired.runtime.channel_router,
            ),
            terminated=False,
            done_reason="",
            release_detail="",
        )
        rendered[agent_id] = json.loads(
            await wired.scenario.read_notifications(agent_id=agent_id, wake=wake)
        )
    assert rendered["ben"]["messages"] == ["ana: K-ABC=1234"]
    assert rendered["ana"]["messages"] == []
    assert rendered["ben"]["notice"] is None
