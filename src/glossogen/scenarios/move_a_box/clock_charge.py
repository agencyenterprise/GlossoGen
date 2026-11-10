"""The output tokens the clock charges a move_a_box response under ``virtual_list_cost_fixed``.

Providers report a response's output tokens as one count, which includes the
list of steps in each ``act`` call. Under ``virtual_list_cost_fixed`` each
list is charged a fixed number of seconds instead: its own tokens, estimated
from the length of its compact JSON, come off the count, and the fixed cost,
converted to tokens at the clock's rate, goes on.
"""

import json
from collections.abc import Sequence

from glossogen.models.tool_definition import ToolCallRequest
from glossogen.scenarios.move_a_box.ids import ACT_TOOL

CHARS_PER_TOKEN = 4.0
"""Characters of compact JSON per output token, used to estimate a list's tokens."""


def estimated_list_tokens(steps: Sequence[object]) -> int:
    """The output tokens a list of ``act`` steps is estimated to take."""
    return round(len(json.dumps(list(steps), separators=(",", ":"))) / CHARS_PER_TOKEN)


def charged_output_tokens(
    output_tokens: int,
    tool_calls: list[ToolCallRequest],
    list_cost_s: float,
    tokens_per_second: float,
) -> int:
    """``output_tokens`` with each ``act`` list's estimated tokens replaced by ``list_cost_s``.

    The count never goes below the fixed costs alone, so an estimate larger than
    the reported count charges nothing for the rest of the response.
    """
    lists = [
        call.arguments["steps"]
        for call in tool_calls
        if call.tool_name == ACT_TOOL and isinstance(call.arguments.get("steps"), list)
    ]
    list_tokens = sum(estimated_list_tokens(steps=steps) for steps in lists)
    fixed_tokens = round(list_cost_s * tokens_per_second) * len(lists)
    return max(0, output_tokens - list_tokens) + fixed_tokens
