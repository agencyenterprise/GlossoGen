"""The view of one round a scenario hands the communication metrics.

A scenario builds these through ``ScenarioBase.build_communication_rounds``; the
open-coding and feature-presence metrics feed them to the LLM judge. The helpers
that build them from a log are in
:mod:`glossogen.evaluation.metrics.communication.round_view`.
"""

from typing import NamedTuple


class CommunicationMessageLine(NamedTuple):
    """One message on the scenario's primary channel rendered for the judge prompt."""

    sender_agent_id: str
    channel_id: str
    text: str


class CommunicationRoundView(NamedTuple):
    """One round's transcript + scenario-rendered ground truth.

    ``header`` is the one-line row anchor the prompts use to tag each
    round (e.g. ``"hard case · target Stack 2 Tier 3"`` for the yard
    scenario, ``"stellar_compass_failure"`` for veyru). Free-form text;
    the prompt simply echoes it.

    ``ground_truth_block`` is a scenario-rendered multiline block that
    describes what each agent could see this round and what the round
    wanted (information asymmetry, target outcome). The scenario owns
    this rendering so the judge sees scenario-appropriate framing
    without the metric code knowing any scenario specifics.

    ``messages`` is the ordered list of messages on the scenario's
    primary channel (or its per-team variants) for this round.
    """

    round_number: int
    header: str
    ground_truth_block: str
    messages: list[CommunicationMessageLine]
