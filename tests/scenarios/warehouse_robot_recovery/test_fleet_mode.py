"""The fleet mode is a closed set that serializes as the phrases recorded runs carry."""

from glossogen.scenarios.warehouse_robot_recovery.events import WarehouseCaseStarted
from glossogen.scenarios.warehouse_robot_recovery.fleet_mode import FleetMode
from glossogen.scenarios.warehouse_robot_recovery.warehouse_cases import get_cases


def test_fleet_mode_serializes_as_its_phrase() -> None:
    event = WarehouseCaseStarted(
        round_number=1,
        case_number=1,
        robot_id="robot 12",
        aisle="aisle 1",
        bay="bay A",
        robot_model="Picker-X1",
        firmware_state="firmware 3.1 stable",
        fleet_mode=FleetMode.HUMAN_PICK_PACK_ZONE_ACTIVE,
        faults=[],
        required_step_order=[],
        forbidden_actions=[],
        aisle_locked=False,
        safety_notes=[],
        time_budget_seconds=600,
    )
    assert '"fleet_mode":"human pick-pack zone active"' in event.model_dump_json()
    reparsed = WarehouseCaseStarted.model_validate_json(event.model_dump_json())
    assert reparsed.fleet_mode is FleetMode.HUMAN_PICK_PACK_ZONE_ACTIVE


def test_every_generated_case_carries_a_fleet_mode_and_its_traffic_note() -> None:
    cases = get_cases(
        seed=42, round_count=40, round_time_budget_seconds=600, fault_count_min=1, fault_count_max=3
    )
    assert {case.fleet_mode for case in cases} == set(FleetMode)
    for case in cases:
        assert len(case.safety_state.notes) == 2
        if case.fleet_mode is FleetMode.HUMAN_PICK_PACK_ZONE_ACTIVE:
            assert "manually move the robot" in case.safety_state.forbidden_actions
