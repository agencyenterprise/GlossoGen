"""``virtual_list_cost_fixed``: the clock charges each ``act`` list a fixed time."""

from collections.abc import Sequence

from glossogen.models.tool_definition import ToolCallRequest
from glossogen.scenarios.move_a_box.clock_charge import (
    charged_output_tokens,
    estimated_list_tokens,
)

DRAG_DOWN = {"action": "drag", "direction": "down"}
TOKENS_PER_SECOND = 50.0


def act_call(steps: Sequence[object]) -> ToolCallRequest:
    return ToolCallRequest(
        call_id="call-1", tool_name="act", arguments={"steps": list(steps), "reasoning": "Go."}
    )


def test_an_act_list_costs_its_fixed_time_in_place_of_its_tokens() -> None:
    steps = [DRAG_DOWN] * 10
    charged = charged_output_tokens(
        output_tokens=estimated_list_tokens(steps=steps) + 40,
        tool_calls=[act_call(steps=steps)],
        list_cost_s=1.0,
        tokens_per_second=TOKENS_PER_SECOND,
    )
    assert charged == 40 + 50


def test_a_long_list_and_a_short_one_cost_the_same() -> None:
    """With the same tokens outside the list, list length no longer changes the charge."""
    charges = [
        charged_output_tokens(
            output_tokens=estimated_list_tokens(steps=steps) + 25,
            tool_calls=[act_call(steps=steps)],
            list_cost_s=0.5,
            tokens_per_second=TOKENS_PER_SECOND,
        )
        for steps in ([DRAG_DOWN], [DRAG_DOWN] * 20)
    ]
    assert charges == [25 + 25, 25 + 25]


def test_calls_other_than_act_are_charged_by_their_tokens() -> None:
    wait = ToolCallRequest(
        call_id="call-1", tool_name="read_notifications", arguments={"wait_for": "next_round"}
    )
    assert (
        charged_output_tokens(
            output_tokens=120,
            tool_calls=[wait],
            list_cost_s=1.0,
            tokens_per_second=TOKENS_PER_SECOND,
        )
        == 120
    )


def test_an_estimate_above_the_reported_count_leaves_only_the_fixed_cost() -> None:
    assert (
        charged_output_tokens(
            output_tokens=5,
            tool_calls=[act_call(steps=[DRAG_DOWN] * 40)],
            list_cost_s=1.0,
            tokens_per_second=TOKENS_PER_SECOND,
        )
        == 50
    )
