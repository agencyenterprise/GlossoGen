"""Assembles LLM message sequences from channel histories and scenario metadata.

Provides :class:`PromptBuilder`, which collects channel messages visible to a
given agent, converts them into ``LLMMessage`` objects with role and sender
annotations, and merges consecutive same-role messages before returning the
final prompt sequence.
"""

import logging

from schmidt.channel_router import ChannelRouter
from schmidt.llm.provider import LLMMessage
from schmidt.models.message import SimulationMessage
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds a list of ``LLMMessage`` objects representing the
    prompt for one agent turn.

    Gathers full message history from all visible channels, converts
    each message into an ``LLMMessage`` with appropriate role and
    sender prefix.
    """

    def __init__(
        self,
        scenario: SimulationScenario,
        channel_router: ChannelRouter,
    ) -> None:
        self._scenario = scenario
        self._channel_router = channel_router

    def build_messages(
        self,
        agent_id: str,
        visible_channel_ids: list[str],
        injection: str | None,
    ) -> list[LLMMessage]:
        """Build the LLM message list for a single agent turn.

        Collects the full history from all visible channels, sorts them
        chronologically, and maps each one to an ``LLMMessage``.  Messages
        sent by ``agent_id`` become ``"assistant"`` messages; all others
        become ``"user"`` messages prefixed with channel display name and
        sender role.  If ``injection`` is provided it is appended after
        history as a ``"user"`` message.  Consecutive messages with the
        same role are merged before returning.
        """
        all_messages: list[SimulationMessage] = []

        for channel_id in visible_channel_ids:
            history = self._channel_router.get_history(channel_id=channel_id)
            all_messages.extend(history)

        all_messages.sort(key=lambda m: m.timestamp)

        llm_messages: list[LLMMessage] = []

        for msg in all_messages:
            if msg.sender_agent_id == agent_id:
                llm_messages.append(LLMMessage(role="assistant", content=msg.text))
            else:
                display_name = self._scenario.get_channel_display_name(
                    channel_id=msg.channel_id, agent_id=agent_id
                )
                sender_role = self._scenario.get_agent_display_name(agent_id=msg.sender_agent_id)
                prefix = f"[{display_name}] {sender_role}"
                llm_messages.append(LLMMessage(role="user", content=f"{prefix}: {msg.text}"))

        if injection is not None:
            llm_messages.append(LLMMessage(role="user", content=injection))

        merged = _merge_consecutive_roles(messages=llm_messages)
        logger.debug(
            "Built prompt for agent %s: %d channel messages, %d merged LLM messages, injection=%s",
            agent_id,
            len(all_messages),
            len(merged),
            injection is not None,
        )
        return merged


def _merge_consecutive_roles(messages: list[LLMMessage]) -> list[LLMMessage]:
    """Merge adjacent messages that share the same role by joining their content.

    When two or more consecutive ``LLMMessage`` objects have the same
    ``role`` and both have ``str`` content, they are combined into a single
    message with their texts separated by a blank line.  Messages with
    non-string content are never merged.
    """
    if not messages:
        return []

    merged: list[LLMMessage] = [messages[0]]
    for msg in messages[1:]:
        if (
            msg.role == merged[-1].role
            and isinstance(msg.content, str)
            and isinstance(merged[-1].content, str)
        ):
            merged[-1] = LLMMessage(
                role=msg.role,
                content=f"{merged[-1].content}\n\n{msg.content}",
            )
        else:
            merged.append(msg)

    return merged
