"""One agent's running cost, shared by every runner.

A runner adds usage as it learns of it, per cycle or per response. Each batch is
priced at the rates in effect when it is added, the same rule the run views
apply to each logged usage, so a rate that changes during a run, by date or by
time of day, applies only to the tokens spent under it. The total is published
on the event bus for the live viewer and written to the supervisor's
``cost_tracker`` so the cost survives the runner's task being cancelled at
shutdown. An agent whose model the pricing table does not know reports no cost.
"""

from datetime import UTC, datetime

from glossogen.event_bus import EventBus
from glossogen.model_catalog import Provider
from glossogen.server.runs.streaming_event import AgentCostUpdated
from glossogen.token_pricing import compute_token_cost_usd, find_pricing


class AgentCostAccumulator:
    """Adds up one agent's cost across cycles and keeps it published."""

    def __init__(
        self,
        agent_id: str,
        model: str,
        provider: Provider,
        event_bus: EventBus,
        cost_tracker: dict[str, float],
    ) -> None:
        self._agent_id = agent_id
        self._model = model
        self._provider = provider
        self._event_bus = event_bus
        self._cost_tracker = cost_tracker
        self._cumulative_cost_usd = 0.0

    @property
    def cumulative_cost_usd(self) -> float:
        """The agent's cost so far; zero while its model is unpriced."""
        return self._cumulative_cost_usd

    def add_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        """Price one batch of usage now, then publish and record the new cumulative cost."""
        pricing = find_pricing(model=self._model, provider=self._provider, at=datetime.now(tz=UTC))
        if pricing is None:
            return
        self._cumulative_cost_usd += compute_token_cost_usd(
            pricing=pricing,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        self._event_bus.publish(
            event=AgentCostUpdated(
                agent_id=self._agent_id,
                cumulative_cost_usd=self._cumulative_cost_usd,
            ).model_dump(mode="json")
        )
        self._cost_tracker[self._agent_id] = self._cumulative_cost_usd
