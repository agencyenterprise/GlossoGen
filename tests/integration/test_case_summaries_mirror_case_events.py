"""Each scenario's run-detail case summary carries its case-start event's fields unchanged.

One scripted round is played per scenario, and every summary in its extras is
compared with the case-start event it came from, field by field and into nested
stages, on the fields the summary declares.
"""

from pathlib import Path

import pytest
from pydantic import JsonValue

from glossogen.models.event_base import EventBase
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenarios.container_yard_stacking.events import ContainerYardCaseStarted
from glossogen.scenarios.drive_module_repair.events import DriveModuleCaseStarted
from glossogen.scenarios.orbital_anomaly.events import OrbitalAnomalyCaseStarted
from glossogen.scenarios.spot_the_difference.events import SpotTheDifferenceCaseStarted
from glossogen.scenarios.veyru.events import VeyruCaseStarted
from glossogen.testing.scenario_runtime import run_rounds

CASE_STARTED_BY_SCENARIO: dict[str, type[EventBase]] = {
    "container_yard_stacking": ContainerYardCaseStarted,
    "drive_module_repair": DriveModuleCaseStarted,
    "orbital_anomaly": OrbitalAnomalyCaseStarted,
    "spot_the_difference": SpotTheDifferenceCaseStarted,
    "veyru": VeyruCaseStarted,
}


def project(source: JsonValue, shape: JsonValue) -> JsonValue:
    """``source`` cut down to the keys ``shape`` has, at every level of nesting."""
    if isinstance(shape, dict) and isinstance(source, dict):
        return {key: project(source=source[key], shape=shape[key]) for key in shape}
    if isinstance(shape, list) and isinstance(source, list) and len(shape) == len(source):
        return [project(source=item, shape=part) for item, part in zip(source, shape, strict=True)]
    return source


@pytest.mark.parametrize("scenario_name", sorted(CASE_STARTED_BY_SCENARIO))
async def test_every_case_summary_mirrors_its_case_started_event(
    scenario_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_rounds(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    extension = get_scenario_class(name=scenario_name).run_detail_extension()
    assert extension is not None
    extras = extension.build_extras(events=result.events, agents_by_id={}, messages=[])

    started = result.of_type(event_type=CASE_STARTED_BY_SCENARIO[scenario_name])
    cases = extras.model_dump(mode="json")["cases"]
    assert len(started) == 2
    assert [case["round_number"] for case in cases] == [event.round_number for event in started]
    for case, event in zip(cases, started, strict=True):
        assert case == project(source=event.model_dump(mode="json"), shape=case)
