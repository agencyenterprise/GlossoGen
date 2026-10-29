"""``thermal_excess`` over move_a_box rounds played by scripted operators."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.move_a_box.evaluation.thermal_excess_metric import (
    ThermalExcessMetric,
    excess_in,
)
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    build,
    finish,
    haul,
    pack_ice,
    play,
    read,
    stand_by,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


async def measure(
    metric: Metric,
    scenario: MoveABoxScenario,
    events: list[SimulationEvent],
    tmp_path: Path,
) -> list[Measurement]:
    return await metric.compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


def test_one_method_all_round_is_no_excess() -> None:
    assert excess_in(actions=["cart"] * 6) == 0


def test_a_cooling_action_counts() -> None:
    assert excess_in(actions=["cart", "pack_ice", "cart"]) == 1
    assert excess_in(actions=["cart", "stand_by", "pack_ice"]) == 2


def test_each_change_of_method_counts_once() -> None:
    assert excess_in(actions=["cart", "sled"]) == 1
    assert excess_in(actions=["cart", "sled", "cart"]) == 2
    assert excess_in(actions=["drag", "drag", "drag"]) == 0


async def test_thermal_excess_is_zero_when_nobody_varies_the_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()]
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(
        metric=ThermalExcessMetric(), scenario=scenario, events=result.events, tmp_path=tmp_path
    )
    assert measurement.score == 0.0


async def test_thermal_excess_counts_what_one_operator_spent_on_the_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_a: drag, stand_by, pack_ice, sled, cart — two cooling actions, two changes."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul(method="drag", direction="right"),
            stand_by(),
            pack_ice(),
            haul(method="sled", direction="right"),
            haul(method="cart", direction="down"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(
        metric=ThermalExcessMetric(), scenario=scenario, events=result.events, tmp_path=tmp_path
    )
    by_agent = {observation.agent_id: observation.value for observation in measurement.per_agent}
    assert by_agent[OPERATOR_A] == 4.0
    assert by_agent[OPERATOR_B] == 0.0
    assert measurement.score == 2.0


async def test_thermal_excess_skips_a_run_with_no_rounds(tmp_path: Path) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    assert (
        await measure(metric=ThermalExcessMetric(), scenario=scenario, events=[], tmp_path=tmp_path)
        == []
    )
