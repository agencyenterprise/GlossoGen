"""Tool and trigger names, template names and the enums signal_game_server shares.

The players and the palette are signal_game's, so a seed draws the same grids in both
scenarios.
"""

from enum import Enum

END_ROUND_TOOL = "end_round"
RUN_COMMAND_TOOL = "run_command"
"""The shell on the shared server."""

HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel."""

BOTH_CHOSE_TRIGGER = "both_chose"
"""The round ended because each player called end_round."""

DESCRIPTION_TEMPLATE = "description.jinja"
SYSTEM_TEMPLATE = "player_system.jinja"
INJECTION_TEMPLATE = "player_injection.jinja"
BOARD_TEMPLATE = "board_view.jinja"
PROTOCOL_SUFFIX_TEMPLATE = "protocol_suffix.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"
JUDGE_SYSTEM_TEMPLATE = "plaintext_judge_system.jinja"
JUDGE_TEXTS_TEMPLATE = "plaintext_judge_texts.jinja"


class WrittenTextKind(str, Enum):
    """What a text the plaintext judge reads is: what a file holds, or what a node is called."""

    CONTENT = "content"
    NAME = "name"


class JudgeTool(str, Enum):
    """A tool the plaintext judge investigates with: a shell on a copy of the server, or a
    Python program run in the sandbox over a dump of it."""

    SHELL = "run_command"
    PYTHON = "run_python"
