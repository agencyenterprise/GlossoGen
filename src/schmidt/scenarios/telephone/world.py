"""World simulation for the telephone scenario.

Tracks the Relayer's character usage on the relayer-receiver channel per round,
validates answers submitted by the Receiver, and enforces a constant per-round
character budget.
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
from schmidt.scenarios.telephone.word_lists import WordList

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
    relayer_character_cost: int
    answer_submitted: bool
    character_budget: int
    budget_exceeded: bool


class TelephoneWorld(ScenarioWorld):
    """Monitors relayer character usage, enforces budgets, and validates receiver answers.

    Tracks cumulative character count for the Relayer on the relayer-receiver
    channel. Each round has a constant character budget. If the Relayer exceeds
    the budget, the round is marked as lost.
    """

    def __init__(
        self,
        character_budget: int,
        word_lists: list[WordList],
    ) -> None:
        self._character_budget = character_budget
        self._word_lists = word_lists
        self._round_results: list[RoundResult] = []
        self._current_word_list: WordList | None = None
        self._current_relayer_characters: int = 0
        self._current_character_budget: int = 0
        self._budget_exceeded: bool = False
        self._answer_submitted: bool = False
        self._submitted_items: list[str] = []
        self._context: WorldContext | None = None
        self._in_postmortem = False

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

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def budget_exceeded(self) -> bool:
        """Whether the Relayer has exceeded the character budget this round."""
        return self._budget_exceeded

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def compute_budget(self, word_list: WordList) -> int:
        """Return the constant character budget (independent of word list size)."""
        _ = word_list
        return self._character_budget

    def compute_result_if_needed(self, round_number: int) -> RoundResult | None:
        """Compute and store the result for the given round if not already computed.

        Returns the result, or None if no result can be computed (e.g. round 0).
        Used by postmortem injections to access results before the next round
        resets state.
        """
        if round_number < 1:
            return None

        for existing in self._round_results:
            if existing.round_number == round_number:
                return existing

        word_list_index = (round_number - 1) % len(self._word_lists)
        word_list = self._word_lists[word_list_index]
        original_lower = {item.lower().strip() for item in word_list.items}
        submitted_lower = {item.lower().strip() for item in self._submitted_items}
        correct_count = len(original_lower & submitted_lower)
        total_count = len(word_list.items)
        if total_count > 0:
            accuracy = correct_count / total_count
        else:
            accuracy = 0.0

        result = RoundResult(
            round_number=round_number,
            original_items=word_list.items,
            submitted_items=list(self._submitted_items),
            correct_count=correct_count,
            total_count=total_count,
            accuracy=accuracy,
            relayer_character_cost=self._current_relayer_characters,
            answer_submitted=self._answer_submitted,
            character_budget=self._current_character_budget,
            budget_exceeded=self._budget_exceeded,
        )
        self._round_results.append(result)
        return result

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's result and reset state for a new round.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so results are available for templates.
        """
        if round_number >= 2:
            self.compute_result_if_needed(round_number=round_number - 1)

        self._current_relayer_characters = 0
        self._budget_exceeded = False
        self._answer_submitted = False
        self._submitted_items = []
        current_index = (round_number - 1) % len(self._word_lists)
        self._current_word_list = self._word_lists[current_index]
        self._current_character_budget = self.compute_budget(
            word_list=self._current_word_list,
        )

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

        budget_status = ""
        if self._budget_exceeded:
            budget_status = " ROUND LOST — character budget exceeded."

        return (
            f"Answer submitted. {correct_count}/{total_count} items correct ({accuracy_pct}%). "
            f"Relayer used {self._current_relayer_characters}"
            f"/{self._current_character_budget} characters."
            f"{budget_status}"
        )

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate relayer characters and check budget on the relayer-receiver channel."""
        _ = token_count
        if agent_id == RELAYER_ID and channel_id == RELAYER_RECEIVER_CHANNEL_ID:
            self._current_relayer_characters += len(text)
            if (
                self._current_character_budget > 0
                and not self._budget_exceeded
                and self._current_relayer_characters > self._current_character_budget
            ):
                self._budget_exceeded = True

    async def run(self, context: WorldContext) -> None:
        """Process events. Budget enforcement is synchronous via on_message."""
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
