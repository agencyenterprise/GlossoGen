"""Shared prompts and constants for the agent communication protocol.

Agents use the communication protocol unless their scenario selects
``workspace_action``; the choice is preserved in registration events for replay.
Prompt text lives in Jinja2 templates under ``runners/prompts/``.
"""

from collections.abc import Collection
from pathlib import Path

from glossogen.models.interaction_protocol import InteractionProtocol, is_workspace_action_protocol
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

SEND_TOOL_NAME = "send"
"""The ``workspace_action`` message tool. An agent without it cannot message."""

WAIT_FOR_MESSAGE_TOOL_NAME = "wait_for_message"
"""Suspends a ``workspace_action`` agent until a message, a lifecycle event or a timeout."""

FINISH_TOOL_NAME = "finish"
"""Suspends a ``workspace_action`` agent until the next round or the end of the run."""


def can_send(tool_names: Collection[str]) -> bool:
    """Whether a ``workspace_action`` agent with these tools can message.

    The workspace prompts describe messaging only to such agents.
    """
    return SEND_TOOL_NAME in tool_names


INITIAL_PROMPT = _renderer.render(
    template_name="initial_prompt.jinja",
    template_variables={},
)

CONTINUE_PROMPT = _renderer.render(
    template_name="continue_prompt.jinja",
    template_variables={},
)

COMPACTION_INSTRUCTIONS = _renderer.render(
    template_name="compaction_instructions.jinja",
    template_variables={},
)


def build_full_system_prompt(
    base_prompt: str,
    role_name: str,
    interaction_protocol: InteractionProtocol,
    tool_names: Collection[str],
) -> str:
    """Combine an agent's base system prompt with the instructions for its protocol.

    ``tool_names`` is the agent's registered tool list; the workspace suffix
    leaves out messaging when it has no ``send``.
    """
    template_name = "system_suffix.jinja"
    if is_workspace_action_protocol(interaction_protocol):
        template_name = "workspace_action_suffix.jinja"
    suffix = _renderer.render(
        template_name=template_name,
        template_variables={"role_name": role_name, "can_send": can_send(tool_names=tool_names)},
    )
    return base_prompt + "\n\n" + suffix


def interaction_prompts(
    interaction_protocol: InteractionProtocol, tool_names: Collection[str]
) -> tuple[str, str]:
    """Return the initial and continuation prompts, for execution and reconstruction.

    The workspace prompts name ``send`` only for an agent whose ``tool_names`` has it.
    """
    if not is_workspace_action_protocol(interaction_protocol):
        return INITIAL_PROMPT, CONTINUE_PROMPT
    messaging: dict[str, object] = {"can_send": can_send(tool_names=tool_names)}
    return (
        _renderer.render(
            template_name="workspace_action_initial.jinja", template_variables=messaging
        ),
        _renderer.render(
            template_name="workspace_action_continue.jinja", template_variables=messaging
        ),
    )


def render_implicit_finish_wake_prompt(package_json: str, tool_names: Collection[str]) -> str:
    """The user prompt that resumes a workspace agent whose turn ended in text.

    Such a turn counts as ``finish``, so the agent resumes only on a lifecycle
    event; ``package_json`` is the wake package it would have received.
    """
    return _renderer.render(
        template_name="workspace_action_wake.jinja",
        template_variables={
            "package_json": package_json,
            "can_send": can_send(tool_names=tool_names),
        },
    )
