"""Assembles run detail data into a structure suitable for PDF export.

Mirrors the frontend's mergeEntries() and groupByRoundAndTurn() logic,
producing a round-turn-entry hierarchy with pre-computed agent and channel
colors for the Jinja2 PDF template.
"""

from datetime import datetime

from pydantic import BaseModel

from schmidt.server.response_models import (
    AgentDetail,
    ChannelMessage,
    ReasoningEntry,
    RunDetailResponse,
    ToolUseEntry,
)

# ---------------------------------------------------------------------------
# Color palettes — hex equivalents of Tailwind classes in agent-colors.ts
# ---------------------------------------------------------------------------


class HexColor(BaseModel):
    """A background/foreground hex color pair for PDF rendering."""

    bg: str
    fg: str


AGENT_PALETTE: list[HexColor] = [
    HexColor(bg="#DBEAFE", fg="#1E40AF"),  # blue-100 / blue-800
    HexColor(bg="#FFEDD5", fg="#9A3412"),  # orange-100 / orange-800
    HexColor(bg="#DCFCE7", fg="#166534"),  # green-100 / green-800
    HexColor(bg="#F3E8FF", fg="#6B21A8"),  # purple-100 / purple-800
    HexColor(bg="#F5F5F4", fg="#57534E"),  # stone-100 / stone-600
    HexColor(bg="#FFE4E6", fg="#9F1239"),  # rose-100 / rose-800
    HexColor(bg="#CFFAFE", fg="#155E75"),  # cyan-100 / cyan-800
    HexColor(bg="#FEF3C7", fg="#92400E"),  # amber-100 / amber-800
]

CHANNEL_PALETTE: list[HexColor] = [
    HexColor(bg="#EFF6FF", fg="#1D4ED8"),  # blue-50 / blue-700
    HexColor(bg="#FFFBEB", fg="#B45309"),  # amber-50 / amber-700
    HexColor(bg="#ECFDF5", fg="#047857"),  # emerald-50 / emerald-700
    HexColor(bg="#FFF1F2", fg="#BE123C"),  # rose-50 / rose-700
]


def get_agent_color(index: int) -> HexColor:
    return AGENT_PALETTE[index % len(AGENT_PALETTE)]


def get_channel_color(index: int) -> HexColor:
    return CHANNEL_PALETTE[index % len(CHANNEL_PALETTE)]


def derive_initials(role_name: str) -> str:
    """Derive two-letter initials from a role name, matching the frontend logic."""
    words = role_name.strip().split()
    words = [w for w in words if len(w) > 0]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    two_chars = role_name.strip()[:2]
    if len(two_chars) == 0:
        return "?"
    return two_chars.upper()


# ---------------------------------------------------------------------------
# Display entry — unified message/reasoning/tool-use type
# ---------------------------------------------------------------------------


class PdfDisplayEntry(BaseModel):
    """Unified display entry merging channel messages, reasoning, and tool use."""

    message_id: str
    channel_id: str
    channel_ids: list[str]
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int
    is_reasoning: bool
    is_tool_use: bool
    tool_name: str
    tool_arguments: dict[str, object]
    tool_result: str | None
    channel_color: HexColor | None


class PdfTurnGroup(BaseModel):
    """Entries grouped by a single agent turn within a round."""

    agent_id: str
    agent_role_name: str
    agent_initials: str
    agent_color: HexColor
    timestamp: datetime
    entries: list[PdfDisplayEntry]


class PdfRoundGroup(BaseModel):
    """Turn groups for a single simulation round."""

    round_number: int
    turns: list[PdfTurnGroup]


class PdfExportData(BaseModel):
    """Top-level container for all data needed by the PDF template."""

    scenario_name: str
    scenario_description: str
    timestamp: datetime
    total_messages: int
    channel_filter: str | None
    agents: list[AgentDetail]
    rounds: list[PdfRoundGroup]


# ---------------------------------------------------------------------------
# Assembly functions
# ---------------------------------------------------------------------------


def _merge_display_entries(
    messages: list[ChannelMessage],
    reasoning: list[ReasoningEntry],
    tool_use: list[ToolUseEntry],
    channel_color_map: dict[str, HexColor],
) -> list[PdfDisplayEntry]:
    """Merge channel messages, reasoning, and tool uses into a sorted timeline."""
    entries: list[PdfDisplayEntry] = []

    for m in messages:
        entries.append(
            PdfDisplayEntry(
                message_id=m.message_id,
                channel_id=m.channel_id,
                channel_ids=[m.channel_id],
                sender_agent_id=m.sender_agent_id,
                text=m.text,
                timestamp=m.timestamp,
                round_number=m.round_number,
                is_reasoning=False,
                is_tool_use=False,
                tool_name="",
                tool_arguments={},
                tool_result=None,
                channel_color=channel_color_map.get(m.channel_id),
            )
        )

    for r in reasoning:
        entries.append(
            PdfDisplayEntry(
                message_id=r.message_id,
                channel_id="",
                channel_ids=r.channel_ids,
                sender_agent_id=r.sender_agent_id,
                text=r.text,
                timestamp=r.timestamp,
                round_number=r.round_number,
                is_reasoning=True,
                is_tool_use=False,
                tool_name="",
                tool_arguments={},
                tool_result=None,
                channel_color=None,
            )
        )

    for t in tool_use:
        entries.append(
            PdfDisplayEntry(
                message_id=t.message_id,
                channel_id="",
                channel_ids=[],
                sender_agent_id=t.sender_agent_id,
                text="",
                timestamp=t.timestamp,
                round_number=t.round_number,
                is_reasoning=False,
                is_tool_use=True,
                tool_name=t.tool_name,
                tool_arguments=t.arguments,
                tool_result=t.result,
                channel_color=None,
            )
        )

    entries.sort(key=lambda e: e.timestamp)
    return entries


def _filter_by_channel(
    entries: list[PdfDisplayEntry],
    channel_id: str,
) -> list[PdfDisplayEntry]:
    """Filter entries to a specific channel, keeping linked reasoning."""
    return [e for e in entries if e.is_reasoning or e.is_tool_use or channel_id in e.channel_ids]


def _group_by_round_and_turn(
    entries: list[PdfDisplayEntry],
    agent_map: dict[str, AgentDetail],
    agent_color_map: dict[str, HexColor],
) -> list[PdfRoundGroup]:
    """Group entries hierarchically by round then by agent turn."""
    rounds: list[PdfRoundGroup] = []
    current_round = -1
    current_turns: list[PdfTurnGroup] = []
    current_turn: PdfTurnGroup | None = None

    def _make_turn(entry: PdfDisplayEntry) -> PdfTurnGroup:
        agent = agent_map.get(entry.sender_agent_id)
        role_name = agent.role_name if agent else entry.sender_agent_id
        return PdfTurnGroup(
            agent_id=entry.sender_agent_id,
            agent_role_name=role_name,
            agent_initials=derive_initials(role_name=role_name),
            agent_color=agent_color_map.get(
                entry.sender_agent_id,
                AGENT_PALETTE[0],
            ),
            timestamp=entry.timestamp,
            entries=[entry],
        )

    for entry in entries:
        if entry.round_number != current_round:
            if current_turn is not None:
                current_turns.append(current_turn)
            if len(current_turns) > 0:
                rounds.append(
                    PdfRoundGroup(
                        round_number=current_round,
                        turns=current_turns,
                    )
                )
            current_round = entry.round_number
            current_turns = []
            current_turn = _make_turn(entry=entry)
        elif current_turn is not None and entry.sender_agent_id == current_turn.agent_id:
            current_turn.entries.append(entry)
        else:
            if current_turn is not None:
                current_turns.append(current_turn)
            current_turn = _make_turn(entry=entry)

    if current_turn is not None:
        current_turns.append(current_turn)
    if len(current_turns) > 0:
        rounds.append(
            PdfRoundGroup(
                round_number=current_round,
                turns=current_turns,
            )
        )

    return rounds


def build_pdf_export_data(
    run_detail: RunDetailResponse,
    channel_id: str | None,
) -> PdfExportData:
    """Assemble all data needed for PDF rendering from a RunDetailResponse."""
    agent_color_map: dict[str, HexColor] = {}
    agent_map: dict[str, AgentDetail] = {}
    for idx, agent in enumerate(run_detail.agents):
        agent_color_map[agent.agent_id] = get_agent_color(index=idx)
        agent_map[agent.agent_id] = agent

    channel_color_map: dict[str, HexColor] = {}
    for idx, ch_id in enumerate(run_detail.channel_ids):
        channel_color_map[ch_id] = get_channel_color(index=idx)

    entries = _merge_display_entries(
        messages=run_detail.messages,
        reasoning=run_detail.reasoning,
        tool_use=run_detail.tool_use,
        channel_color_map=channel_color_map,
    )

    if channel_id is not None:
        entries = _filter_by_channel(entries=entries, channel_id=channel_id)

    rounds = _group_by_round_and_turn(
        entries=entries,
        agent_map=agent_map,
        agent_color_map=agent_color_map,
    )

    return PdfExportData(
        scenario_name=run_detail.scenario_name,
        scenario_description=run_detail.scenario_description,
        timestamp=run_detail.timestamp,
        total_messages=run_detail.total_messages,
        channel_filter=channel_id,
        agents=run_detail.agents,
        rounds=rounds,
    )
