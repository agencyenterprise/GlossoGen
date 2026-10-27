"""How a run's messages, reasoning and tool calls become the PDF's rounds and turns.

`build_pdf_export_data` reads the header fields, the roster, the channels and the
entry lists of a `RunDetailResponse`, so the detail here is built with
`model_construct` and those fields alone. Every timestamp is fixed, because the
timeline is ordered by them.
"""

from datetime import UTC, datetime, timedelta

import pytest

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.pdf.export_data import (
    AGENT_PALETTE,
    CHANNEL_PALETTE,
    PdfExportData,
    build_pdf_export_data,
    derive_initials,
)
from glossogen.server.runs.models import (
    ReasoningEntry,
    ReasoningKind,
    RunDetailResponse,
    ToolUseEntry,
)

START = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    """A fixed instant ``seconds`` after the run started."""
    return START + timedelta(seconds=seconds)


def agent(agent_id: str, role_name: str) -> AgentDetail:
    """One roster entry; only the id and role name reach the PDF's turns."""
    return AgentDetail(
        agent_id=agent_id,
        role_name=role_name,
        channel_ids=["link", "ops"],
        tool_names=["send_message"],
        model="opus",
        provider="anthropic",
        model_settings=AgentModelSettings(max_tokens=1024),
        system_prompt="",
    )


def message(
    message_id: str, sender: str, channel_id: str, seconds: int, round_number: int
) -> ChannelMessage:
    """A channel message sent at ``seconds``."""
    return ChannelMessage(
        message_id=message_id,
        channel_id=channel_id,
        sender_agent_id=sender,
        sender_display_name=sender,
        text=f"{message_id} text",
        timestamp=at(seconds=seconds),
        round_number=round_number,
        token_count=1,
    )


def reasoning(
    message_id: str, sender: str, channel_ids: list[str], seconds: int, round_number: int
) -> ReasoningEntry:
    """Reasoning linked to the channels of the agent's surrounding sends."""
    return ReasoningEntry(
        message_id=message_id,
        sender_agent_id=sender,
        kind=ReasoningKind.THINKING,
        text=f"{message_id} text",
        timestamp=at(seconds=seconds),
        round_number=round_number,
        channel_ids=channel_ids,
    )


def tool_use(message_id: str, sender: str, seconds: int, round_number: int) -> ToolUseEntry:
    """A finished tool call."""
    return ToolUseEntry(
        message_id=message_id,
        sender_agent_id=sender,
        tool_name="inspect",
        call_id=f"call-{message_id}",
        arguments={"target": "panel"},
        result="ok",
        timestamp=at(seconds=seconds),
        result_timestamp=at(seconds=seconds),
        round_number=round_number,
        result_round_number=round_number,
    )


def run_detail(
    agents: list[AgentDetail],
    channel_ids: list[str],
    messages: list[ChannelMessage],
    reasoning_entries: list[ReasoningEntry],
    tool_use_entries: list[ToolUseEntry],
) -> RunDetailResponse:
    """A run detail carrying the fields the PDF export reads."""
    return RunDetailResponse.model_construct(
        scenario_name="veyru",
        scenario_description="A test run.",
        timestamp=START,
        total_messages=len(messages),
        channel_ids=channel_ids,
        agents=agents,
        messages=messages,
        reasoning=reasoning_entries,
        tool_use=tool_use_entries,
    )


ALICE = agent(agent_id="alice", role_name="Field Observer")
BOB = agent(agent_id="bob", role_name="Engineer")


def layout(data: PdfExportData) -> list[tuple[int, list[tuple[str, list[str]]]]]:
    """Each round as its number and its turns, each turn as its agent and entry ids."""
    return [
        (
            round_group.round_number,
            [(turn.agent_id, [e.message_id for e in turn.entries]) for turn in round_group.turns],
        )
        for round_group in data.rounds
    ]


def test_entries_are_ordered_by_time_and_grouped_into_rounds_and_turns() -> None:
    """A turn is one agent's consecutive entries; a new round starts a new turn."""
    detail = run_detail(
        agents=[ALICE, BOB],
        channel_ids=["link"],
        # Passed out of order and split across the three lists, as the reader returns them.
        messages=[
            message(message_id="m2", sender="bob", channel_id="link", seconds=4, round_number=1),
            message(message_id="m1", sender="alice", channel_id="link", seconds=2, round_number=1),
            message(message_id="m3", sender="bob", channel_id="link", seconds=10, round_number=2),
        ],
        reasoning_entries=[
            reasoning(
                message_id="r1", sender="alice", channel_ids=["link"], seconds=1, round_number=1
            ),
            reasoning(
                message_id="r3", sender="alice", channel_ids=["link"], seconds=5, round_number=1
            ),
        ],
        tool_use_entries=[
            tool_use(message_id="t1", sender="alice", seconds=3, round_number=1),
            tool_use(message_id="t2", sender="bob", seconds=11, round_number=2),
        ],
    )

    data = build_pdf_export_data(run_detail=detail, channel_id=None)

    assert layout(data=data) == [
        (1, [("alice", ["r1", "m1", "t1"]), ("bob", ["m2"]), ("alice", ["r3"])]),
        (2, [("bob", ["m3", "t2"])]),
    ]


def test_turns_are_numbered_from_one_within_each_round() -> None:
    """The run viewer numbers turns the same way, restarting at each round."""
    detail = run_detail(
        agents=[ALICE, BOB],
        channel_ids=["link"],
        messages=[
            message(message_id="m1", sender="alice", channel_id="link", seconds=1, round_number=1),
            message(message_id="m2", sender="bob", channel_id="link", seconds=2, round_number=1),
            message(message_id="m3", sender="alice", channel_id="link", seconds=3, round_number=1),
            message(message_id="m4", sender="alice", channel_id="link", seconds=4, round_number=2),
        ],
        reasoning_entries=[],
        tool_use_entries=[],
    )

    data = build_pdf_export_data(run_detail=detail, channel_id=None)

    assert [[turn.turn_number for turn in r.turns] for r in data.rounds] == [[1, 2, 3], [1]]


def test_each_entry_kind_keeps_what_the_template_renders() -> None:
    detail = run_detail(
        agents=[ALICE],
        channel_ids=["link"],
        messages=[
            message(message_id="m1", sender="alice", channel_id="link", seconds=1, round_number=1)
        ],
        reasoning_entries=[
            reasoning(
                message_id="r1", sender="alice", channel_ids=["link"], seconds=2, round_number=1
            )
        ],
        tool_use_entries=[tool_use(message_id="t1", sender="alice", seconds=3, round_number=1)],
    )

    [round_group] = build_pdf_export_data(run_detail=detail, channel_id=None).rounds
    sent, thought, called = round_group.turns[0].entries

    assert (sent.is_reasoning, sent.is_tool_use, sent.channel_id, sent.text) == (
        False,
        False,
        "link",
        "m1 text",
    )
    assert (thought.is_reasoning, thought.is_tool_use, thought.text) == (True, False, "r1 text")
    assert (called.is_tool_use, called.tool_name, called.tool_arguments, called.tool_result) == (
        True,
        "inspect",
        {"target": "panel"},
        "ok",
    )


def test_a_run_with_no_entries_has_no_rounds() -> None:
    detail = run_detail(
        agents=[ALICE], channel_ids=["link"], messages=[], reasoning_entries=[], tool_use_entries=[]
    )

    assert build_pdf_export_data(run_detail=detail, channel_id=None).rounds == []


def test_agents_and_channels_take_palette_colours_in_roster_order_and_wrap() -> None:
    """Colours follow position in the roster and channel list, as in the run viewer."""
    # Each channel's message is sent by a roster agent, so the roster must be the longer list.
    assert len(CHANNEL_PALETTE) < len(AGENT_PALETTE)
    agents = [
        agent(agent_id=f"a{i}", role_name=f"Agent {i}") for i in range(len(AGENT_PALETTE) + 1)
    ]
    channel_ids = [f"c{i}" for i in range(len(CHANNEL_PALETTE) + 1)]
    messages = [
        message(message_id=f"m{i}", sender=f"a{i}", channel_id=f"c{i}", seconds=i, round_number=1)
        for i in range(len(CHANNEL_PALETTE) + 1)
    ] + [
        message(
            message_id="last",
            sender=f"a{len(AGENT_PALETTE)}",
            channel_id="c0",
            seconds=100,
            round_number=1,
        )
    ]
    detail = run_detail(
        agents=agents,
        channel_ids=channel_ids,
        messages=messages,
        reasoning_entries=[],
        tool_use_entries=[],
    )

    turns = build_pdf_export_data(run_detail=detail, channel_id=None).rounds[0].turns

    assert turns[0].agent_color == AGENT_PALETTE[0]
    assert turns[1].agent_color == AGENT_PALETTE[1]
    assert turns[-1].agent_color == AGENT_PALETTE[0]
    assert turns[0].entries[0].channel_color == CHANNEL_PALETTE[0]
    assert turns[len(CHANNEL_PALETTE)].entries[0].channel_color == CHANNEL_PALETTE[0]
    assert turns[1].entries[0].channel_color == CHANNEL_PALETTE[1]


def test_a_sender_missing_from_the_roster_is_shown_by_its_id() -> None:
    detail = run_detail(
        agents=[ALICE],
        channel_ids=["link"],
        messages=[
            message(
                message_id="m1", sender="narrator", channel_id="link", seconds=1, round_number=1
            )
        ],
        reasoning_entries=[],
        tool_use_entries=[],
    )

    [turn] = build_pdf_export_data(run_detail=detail, channel_id=None).rounds[0].turns

    assert (turn.agent_role_name, turn.agent_initials) == ("narrator", "NA")


def channel_filter_detail() -> RunDetailResponse:
    """Alice on link and Bob on ops, each with linked reasoning, and one tool call by Bob."""
    return run_detail(
        agents=[ALICE, BOB],
        channel_ids=["link", "ops"],
        messages=[
            message(
                message_id="m-link", sender="alice", channel_id="link", seconds=2, round_number=1
            ),
            message(message_id="m-ops", sender="bob", channel_id="ops", seconds=4, round_number=1),
        ],
        reasoning_entries=[
            reasoning(
                message_id="r-link", sender="alice", channel_ids=["link"], seconds=1, round_number=1
            ),
            reasoning(
                message_id="r-ops", sender="bob", channel_ids=["ops"], seconds=3, round_number=1
            ),
        ],
        tool_use_entries=[tool_use(message_id="t-bob", sender="bob", seconds=5, round_number=1)],
    )


def test_a_channel_export_drops_other_channels_messages() -> None:
    data = build_pdf_export_data(run_detail=channel_filter_detail(), channel_id="link")

    entry_ids = [e.message_id for r in data.rounds for t in r.turns for e in t.entries]
    assert "m-link" in entry_ids
    assert "r-link" in entry_ids
    assert "m-ops" not in entry_ids
    assert data.channel_filter == "link"


def test_a_channel_export_drops_reasoning_linked_only_to_another_channel() -> None:
    data = build_pdf_export_data(run_detail=channel_filter_detail(), channel_id="link")

    entry_ids = [e.message_id for r in data.rounds for t in r.turns for e in t.entries]
    assert "r-ops" not in entry_ids


def test_a_channel_export_drops_tool_calls() -> None:
    data = build_pdf_export_data(run_detail=channel_filter_detail(), channel_id="link")

    entry_ids = [e.message_id for r in data.rounds for t in r.turns for e in t.entries]
    assert "t-bob" not in entry_ids


def test_the_message_count_is_the_channel_messages_the_export_holds() -> None:
    """Reasoning and tool calls are left out of the count, as in the run viewer."""
    detail = channel_filter_detail()

    assert build_pdf_export_data(run_detail=detail, channel_id=None).message_count == 2
    assert build_pdf_export_data(run_detail=detail, channel_id="link").message_count == 1


@pytest.mark.parametrize(
    ("role_name", "initials"),
    [
        ("Field Observer", "FO"),
        ("stabilization engineer lead", "SE"),
        ("engineer", "EN"),
        ("  Field   Observer  ", "FO"),
        ("x", "X"),
        ("   ", "?"),
        ("", "?"),
    ],
)
def test_initials_come_from_the_first_two_words_or_the_first_two_letters(
    role_name: str, initials: str
) -> None:
    assert derive_initials(role_name=role_name) == initials
