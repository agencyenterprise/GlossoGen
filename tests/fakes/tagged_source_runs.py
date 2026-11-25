"""Finished smoke runs whose every send names its sender and its round.

Each agent sends ``<prefix>-r<round>`` once per round, behind a ``RoundGate``, so
the round a message lands in is the script's statement rather than the
scheduler's choice. A test that cuts a run's history at a round can then read
which rounds survived from the sent texts alone.
"""

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from glossogen.models.event import SimulationEnded
from glossogen.testing.scripted_agent import PacedTurn, RoundGate, SayTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_round_paced_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

SOURCE_ROUND_COUNT = 2


def speak_each_round(*, prefix: str) -> list[PacedTurn]:
    """One send per source round, tagged with its round: ``<prefix>-r1``, ``<prefix>-r2``."""
    turns: list[PacedTurn] = []
    for round_number in range(1, SOURCE_ROUND_COUNT + 1):
        turns.append(RoundGate(round_number=round_number))
        turns.append(
            ToolTurn(
                tool_name="send_message",
                args={
                    "channel_id": LINK_CHANNEL_ID,
                    "text": f"{prefix}-r{round_number}",
                    "force": True,
                },
            )
        )
        turns.append(SayTurn(text="done"))
    return turns


def build_smoke_scenario(*, round_count: int) -> SmokeScenario:
    """Build the smoke scenario for ``round_count`` rounds."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=round_count,
            max_round_duration_seconds=45,
            model_overrides={},
        )
    )


async def make_tagged_source_run(
    *,
    run_dir: Path,
    tag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Run a two-round source to completion, its sends tagged ``<tag>-<agent>-r<round>``."""
    run_dir.mkdir(parents=True)
    result = await run_round_paced_simulation(
        scenario=build_smoke_scenario(round_count=SOURCE_ROUND_COUNT),
        scripts={
            FIRST_AGENT_ID: speak_each_round(prefix=f"{tag}-first"),
            SECOND_AGENT_ID: speak_each_round(prefix=f"{tag}-second"),
        },
        tmp_path=run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    assert result.of_type(event_type=SimulationEnded), f"source {tag} did not finish"
    sent_rounds = {
        str(m.text): int(m.round_number) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)
    }
    assert sent_rounds[f"{tag}-first-r1"] == 1
    assert sent_rounds[f"{tag}-first-r2"] == 2
    return run_dir


def sent_texts(*, history: list[ModelMessage]) -> list[str]:
    """The ``send_message`` texts an agent's history remembers sending, in order."""
    texts: list[str] = []
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == "send_message":
                texts.append(str(part.args_as_dict()["text"]))
    return texts
