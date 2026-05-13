"""Per-round transcript + scenario-rendered ground truth shared by the three passes.

The open-coding metric (pass 1) and the feature-presence metric (pass
3) feed the LLM judge the same view of each round so their outputs are
commensurable: a one-line ``header`` identifying the round, a
``ground_truth_block`` rendered by the scenario describing what each
agent saw and what the round wanted, and the ordered list of messages
on the scenario's primary channel.

Scenarios build the per-round view through the
``SimulationScenario.build_communication_rounds`` hook. The hook is
the only scenario-specific surface in this pipeline — the metrics and
prompts read ``CommunicationRoundView`` and never branch on scenario
name.
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
