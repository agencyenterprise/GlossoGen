"""World simulation for the car recall scenario.

Delivers shared external events (NHTSA requests, class-action announcements)
as world notifications at the appropriate simulated days. These events were
previously embedded in agent injection templates but are now broadcast to
all agents simultaneously via the world context.
"""

import asyncio
import logging

from schmidt.runtime.scenario_world import (
    MessageEvent,
    RoundAdvancedEvent,
    ScenarioWorld,
    WorldContext,
)
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class CarRecallWorld(ScenarioWorld):
    """Broadcasts shared external events at round transitions.

    Processes ``RoundAdvancedEvent`` from the queue, maps round numbers to
    simulated days, and sends world notifications for external events that
    affect all agents equally (NHTSA reports, lawsuits). Ignores message
    events — car recall has no message-based world logic.
    """

    def __init__(
        self,
        day_map: dict[int, int],
        renderer: TemplateRenderer,
    ) -> None:
        self._day_map = day_map
        self._renderer = renderer

    async def run(self, context: WorldContext) -> None:
        """Process round advance events and broadcast shared external news."""
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    await self._handle_round(
                        round_number=event.round_number,
                        context=context,
                    )
                elif isinstance(event, MessageEvent):
                    pass
        except asyncio.CancelledError:
            return

    async def _handle_round(
        self,
        round_number: int,
        context: WorldContext,
    ) -> None:
        """Send world notifications for the simulated day matching this round."""
        day_number = self._day_map.get(round_number)
        if day_number is None:
            return
        news = self._renderer.render(
            template_name="world_events.jinja",
            template_variables={"day_number": day_number},
        )
        if not news:
            return
        logger.info("Car recall world event for day %d: %d chars", day_number, len(news))
        await context.send_update(text=news)
