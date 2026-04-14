"""World simulation for the telephone scenario.

Tracks the Relayer's token usage on the relayer-receiver channel per round,
validates answers submitted by the Receiver, and stores per-round results
for injection feedback.
"""

import asyncio
import logging
from typing import NamedTuple

from schmidt.runtime.scenario_world import (
    MessageEvent,
    RoundAdvancedEvent,
    ScenarioWorld,
    WorldContext,
)
from schmidt.scenarios.telephone.word_lists import WORD_LISTS, WordList

logger = logging.getLogger(__name__)

RELAYER_ID = "relayer"
RELAYER_RECEIVER_CHANNEL_ID = "relayer_receiver"


class RoundResult(NamedTuple):
    """Outcome of a single telephone round after answer submission or timeout."""

    round_number: int
    original_items: list[str]
    submitted_items: list[str]
    correct_count: int
    total_count: int
    accuracy: float
    relayer_token_cost: int
    answer_submitted: bool


class TelephoneWorld(ScenarioWorld):
    """Monitors relayer token usage and validates receiver answers.

    Tracks cumulative token count for the Relayer on the relayer-receiver
    channel. When the Receiver calls ``submit_answer``, validates against
    the current round's word list using order-independent set matching.
    """

    def __init__(self) -> None:
        self._round_results: list[RoundResult] = []
        self._current_word_list: WordList | None = None
        self._current_relayer_tokens: int = 0
        self._answer_submitted: bool = False
        self._submitted_items: list[str] = []
        self._context: WorldContext | None = None

    @property
    def round_results(self) -> list[RoundResult]:
        """Read-only access to round results for injection templates."""
        return self._round_results

    @property
    def current_word_list(self) -> WordList | None:
        """The word list for the current round."""
        return self._current_word_list

    @property
    def answer_submitted(self) -> bool:
        """Whether the Receiver has submitted an answer this round."""
        return self._answer_submitted

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's result and reset state for a new round.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so results are available for templates.
        """
        previous_round_index = round_number - 2
        if 0 <= previous_round_index < len(WORD_LISTS):
            word_list = WORD_LISTS[previous_round_index]
            original_lower = {item.lower().strip() for item in word_list.items}
            submitted_lower = {item.lower().strip() for item in self._submitted_items}
            correct_count = len(original_lower & submitted_lower)
            total_count = len(word_list.items)
            if total_count > 0:
                accuracy = correct_count / total_count
            else:
                accuracy = 0.0

            self._round_results.append(
                RoundResult(
                    round_number=word_list.round_number,
                    original_items=word_list.items,
                    submitted_items=list(self._submitted_items),
                    correct_count=correct_count,
                    total_count=total_count,
                    accuracy=accuracy,
                    relayer_token_cost=self._current_relayer_tokens,
                    answer_submitted=self._answer_submitted,
                )
            )

        self._current_relayer_tokens = 0
        self._answer_submitted = False
        self._submitted_items = []

        current_index = round_number - 1
        if current_index < len(WORD_LISTS):
            self._current_word_list = WORD_LISTS[current_index]
        else:
            self._current_word_list = None

    def submit_answer(self, items_str: str) -> str:
        """Validate the Receiver's submitted answer against the current word list.

        Returns a result string describing how many items were correct.
        """
        if self._current_word_list is None:
            return "No active round to submit answers for."
        if self._answer_submitted:
            return "Answer already submitted for this round."

        self._submitted_items = [item.strip() for item in items_str.split(",") if item.strip()]
        self._answer_submitted = True

        original_lower = {item.lower().strip() for item in self._current_word_list.items}
        submitted_lower = {item.lower().strip() for item in self._submitted_items}
        correct_count = len(original_lower & submitted_lower)
        total_count = len(self._current_word_list.items)

        if total_count > 0:
            accuracy_pct = int((correct_count / total_count) * 100)
        else:
            accuracy_pct = 0

        return (
            f"Answer submitted. {correct_count}/{total_count} items correct ({accuracy_pct}%). "
            f"Relayer used {self._current_relayer_tokens} tokens."
        )

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate relayer tokens on the relayer-receiver channel.

        Called synchronously from ``send_message`` before the event is
        enqueued.
        """
        _ = text
        if agent_id == RELAYER_ID and channel_id == RELAYER_RECEIVER_CHANNEL_ID:
            self._current_relayer_tokens += token_count

    async def run(self, context: WorldContext) -> None:
        """Process events. Broadcasts result summary after answer submission."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    pass
                elif isinstance(event, MessageEvent):
                    pass
        except asyncio.CancelledError:
            return
