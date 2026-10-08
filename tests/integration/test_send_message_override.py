"""A scenario can replace ``send_message``, and address teammates through direct channels.

The override's parameters become the tool's schema, and it posts through the
runtime's ``publish_message`` and ``direct_channel_for``. Runs the real runner,
MCP server and event log against scripted agents.
"""

import shutil
from collections.abc import Awaitable
from pathlib import Path

import pytest
from pydantic import BaseModel

from glossogen.cli import _resolve_default_visible_channels  # pyright: ignore[reportPrivateUsage]
from glossogen.evaluation.log_reader import load_events
from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.message_rewind import build_rewind_state_at_event
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import ChannelCreated, SimulationEvent
from glossogen.scenario_protocol import PrimaryChannel, SendMessageExecutor
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    BASE_TOOLS,
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

THIRD_AGENT_ID = "third_agent"
AGENT_IDS = (FIRST_AGENT_ID, SECOND_AGENT_ID, THIRD_AGENT_ID)
DIRECT_CHANNEL_ID = f"dm:{FIRST_AGENT_ID}+{SECOND_AGENT_ID}"


class AddressingSmokeScenario(SmokeScenario):
    """Three agents on the smoke link, with a ``send_message`` that takes recipients.

    Three, because addressing every other member of a channel posts to that
    channel: with two agents, naming your one teammate is the whole link.
    """

    _agent_display_names = {
        FIRST_AGENT_ID: "First Agent",
        SECOND_AGENT_ID: "Second Agent",
        THIRD_AGENT_ID: "Third Agent",
    }

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, object] | None) -> list[AgentRole]:
        _ = knobs
        return [
            AgentRole(agent_id=agent_id, role_name=cls._agent_display_names[agent_id])
            for agent_id in AGENT_IDS
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=self.get_agent_display_name(agent_id=agent_id),
                system_prompt=f"You are {agent_id}.",
                channel_ids=[LINK_CHANNEL_ID],
                tool_names=[*BASE_TOOLS, RECORD_TOOL_NAME],
                model=default_model,
                provider=default_provider,
                max_tokens=self.get_knobs().agent_max_tokens,
                compaction=self.get_knobs().compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def get_channels(self) -> list[Channel]:
        return [Channel(channel_id=LINK_CHANNEL_ID, name="link", member_agent_ids=list(AGENT_IDS))]

    def send_message_executor(self) -> SendMessageExecutor:
        return self.send_to

    async def send_to(self, agent_id: str, text: str, to: list[str] | None) -> BaseModel:
        channel_id = LINK_CHANNEL_ID
        if to is not None:
            channel_id = await self.runtime.direct_channel_for(
                agent_id=agent_id, recipient_agent_ids=to
            )
        return await self.runtime.publish_message(
            agent_id=agent_id, channel_id=channel_id, text=text, force=True
        )

    def send_message_description(self) -> str:
        return "Send text to the link, or to the teammates named in to."


def addressing_smoke() -> AddressingSmokeScenario:
    return AddressingSmokeScenario(
        knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
    )


def send(text: str, to: list[str] | None) -> ToolTurn:
    return ToolTurn(tool_name="send_message", args={"text": text, "to": to})


def channels_of(result: SimulationResult) -> dict[str, str]:
    """Each sent message's text, mapped to the channel it landed on."""
    return {
        e["message"]["text"]: e["message"]["channel_id"]
        for e in result.of_type(event_type="message_sent")
    }


async def run_addressing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    return await run_simulation(
        scenario=addressing_smoke(),
        scripts={
            FIRST_AGENT_ID: [
                send(text="to second", to=[SECOND_AGENT_ID]),
                send(text="to both others", to=[SECOND_AGENT_ID, THIRD_AGENT_ID]),
                send(text="to nobody real", to=["nobody"]),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [
                send(text="to first", to=[FIRST_AGENT_ID]),
                send(text="broadcast", to=None),
                SayTurn(text="done"),
            ],
            THIRD_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def test_the_override_signature_is_the_tool_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    registration = result.of_type(event_type="agent_registered")[0]
    definition = next(d for d in registration["tool_definitions"] if d["name"] == "send_message")
    assert set(definition["input_schema"]["properties"]) == {"text", "to"}
    assert definition["description"] == "Send text to the link, or to the teammates named in to."


async def test_addressed_messages_land_on_one_direct_channel_created_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    landed = channels_of(result=result)
    assert landed["to second"] == DIRECT_CHANNEL_ID
    assert landed["to first"] == DIRECT_CHANNEL_ID
    assert landed["broadcast"] == LINK_CHANNEL_ID
    created = result.of_type(event_type="channel_created")
    assert [e["channel_id"] for e in created] == [DIRECT_CHANNEL_ID]
    assert created[0]["member_agent_ids"] == [FIRST_AGENT_ID, SECOND_AGENT_ID]


async def test_addressing_a_whole_channels_membership_posts_to_that_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert channels_of(result=result)["to both others"] == LINK_CHANNEL_ID
    assert len(result.of_type(event_type="channel_created")) == 1


async def test_addressing_someone_outside_the_simulation_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert "to nobody real" not in channels_of(result=result)
    refusals = [
        e["result"]
        for e in result.of_type(event_type="tool_result_received")
        if e["tool_name"] == "send_message" and "not a teammate" in e["result"]
    ]
    assert len(refusals) == 1


async def test_a_resumed_run_restores_the_direct_channel_and_its_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    events = await load_events(log_path=result.log_path)
    last_event_id = events[-1].event_id
    state = build_rewind_state_at_event(
        events=events, target_event_id=last_event_id, cutoff_round=None, agent_filters={}
    )
    assert [channel.channel_id for channel in state.created_channels] == [DIRECT_CHANNEL_ID]
    texts = [message.text for message in state.messages_by_channel[DIRECT_CHANNEL_ID]]
    assert "to second" in texts and "to first" in texts


def created(channel_id: str, members: list[str]) -> SimulationEvent:
    return ChannelCreated(
        round_number=1, channel_id=channel_id, name=channel_id, member_agent_ids=members
    )


def test_a_primary_channel_scores_direct_channels_among_its_members_only_when_asked() -> None:
    scenario = addressing_smoke()
    events = [
        created(channel_id=DIRECT_CHANNEL_ID, members=[FIRST_AGENT_ID, SECOND_AGENT_ID]),
        created(channel_id="dm:first_agent+outsider", members=[FIRST_AGENT_ID, "outsider"]),
    ]
    including = PrimaryChannel(
        channel_id=LINK_CHANNEL_ID, team_id=None, includes_direct_channels=True
    )
    excluding = including._replace(includes_direct_channels=False)
    assert scored_channel_ids(primary=including, scenario=scenario, events=events) == frozenset(
        {LINK_CHANNEL_ID, DIRECT_CHANNEL_ID}
    )
    assert scored_channel_ids(primary=excluding, scenario=scenario, events=events) == frozenset(
        {LINK_CHANNEL_ID}
    )


async def test_replace_agent_visibility_covers_the_direct_channels_an_agent_was_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_addressing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(result.log_path, source / "smoke.jsonl")

    def visible_to(agent_id: str) -> Awaitable[list[str]]:
        return _resolve_default_visible_channels(  # pyright: ignore[reportPrivateUsage]
            source_run_dir=source, scenario_name="smoke", replaced_agent_id=agent_id
        )

    assert await visible_to(agent_id=FIRST_AGENT_ID) == [LINK_CHANNEL_ID, DIRECT_CHANNEL_ID]
    assert await visible_to(agent_id=THIRD_AGENT_ID) == [LINK_CHANNEL_ID]
