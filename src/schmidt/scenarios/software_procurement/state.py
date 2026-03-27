"""Mutable world state for the software procurement scenario.

Tracks proposals, deliverables, cost counters, and acceptance status
across all seller teams during a simulation run.
"""

import logging
from enum import Enum

from pydantic import BaseModel

from schmidt.scenarios.software_procurement.agent_ids import AGENT_TO_TEAM

logger = logging.getLogger(__name__)


class ProposalStatus(str, Enum):
    """Lifecycle status of a seller proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalRecord(BaseModel):
    """A formal proposal submitted by a seller team."""

    team_id: str
    price: int
    description: str
    round_number: int
    status: ProposalStatus


class TeamState(BaseModel):
    """Mutable state for a single seller team."""

    team_id: str
    proposals: list[ProposalRecord]
    deliverable_filename: str | None
    tool_call_count: int


class SoftwareProcurementState:
    """Central mutable state for the procurement scenario.

    Provides methods called by MCP tool executors to record proposals,
    deliverables, and cost. Thread safety is handled by the MCP server
    (one tool call at a time per agent).
    """

    def __init__(self, team_ids: list[str]) -> None:
        self._teams: dict[str, TeamState] = {
            tid: TeamState(
                team_id=tid,
                proposals=[],
                deliverable_filename=None,
                tool_call_count=0,
            )
            for tid in team_ids
        }
        self._accepted_team: str | None = None
        self._current_round = 1

    def get_team_for_agent(self, agent_id: str) -> str:
        """Resolve an agent ID to its team ID."""
        team_id = AGENT_TO_TEAM.get(agent_id)
        if team_id is None:
            raise ValueError(f"Agent {agent_id} is not part of any seller team")
        return team_id

    def increment_tool_calls(self, team_id: str) -> None:
        """Increment the engineering cost counter for a team."""
        self._teams[team_id].tool_call_count += 1

    def get_cost_summary(self, team_id: str) -> str:
        """Return a human-readable cost summary for a team."""
        team = self._teams[team_id]
        return (
            f"Team {team_id} engineering cost: {team.tool_call_count} tool calls. "
            f"Deliverable submitted: {'yes' if team.deliverable_filename else 'no'}."
        )

    def submit_proposal(self, team_id: str, price: int, description: str) -> str:
        """Record a new proposal from a seller team."""
        if self._accepted_team is not None:
            return f"Cannot submit proposal: {self._accepted_team} has already been accepted."

        record = ProposalRecord(
            team_id=team_id,
            price=price,
            description=description,
            round_number=self._current_round,
            status=ProposalStatus.PENDING,
        )
        self._teams[team_id].proposals.append(record)
        logger.info("Team %s submitted proposal: $%d", team_id, price)
        return (
            f"Proposal submitted: ${price}. "
            f"IMPORTANT: The buyer cannot see this proposal automatically. "
            f"You MUST send a message on the negotiation channel to inform "
            f"the buyer that you have submitted a formal proposal at ${price}."
        )

    def accept_proposal(self, team_id: str) -> str:
        """Accept a team's most recent proposal."""
        if self._accepted_team is not None:
            return f"Already accepted a proposal from {self._accepted_team}."

        team = self._teams.get(team_id)
        if team is None:
            return f"Unknown team: {team_id}"

        if not team.proposals:
            return f"Team {team_id} has not submitted any proposals."

        latest = team.proposals[-1]
        latest.status = ProposalStatus.ACCEPTED
        self._accepted_team = team_id
        logger.info("Buyer accepted team %s proposal at $%d", team_id, latest.price)
        return f"Accepted {team_id}'s proposal at ${latest.price}."

    def reject_proposal(self, team_id: str, reason: str) -> str:
        """Reject a team's most recent pending proposal."""
        team = self._teams.get(team_id)
        if team is None:
            return f"Unknown team: {team_id}"

        pending = [p for p in team.proposals if p.status == ProposalStatus.PENDING]
        if not pending:
            return f"Team {team_id} has no pending proposals to reject."

        latest = pending[-1]
        latest.status = ProposalStatus.REJECTED
        logger.info("Buyer rejected team %s proposal: %s", team_id, reason)
        return f"Rejected {team_id}'s proposal. Reason sent: {reason}"

    def record_deliverable(self, team_id: str, filename: str) -> None:
        """Record that a team has submitted a deliverable."""
        self._teams[team_id].deliverable_filename = filename
        logger.info("Team %s submitted deliverable: %s", team_id, filename)

    def has_deliverable(self, team_id: str) -> bool:
        """Check whether a team has submitted a deliverable."""
        team = self._teams.get(team_id)
        if team is None:
            return False
        return team.deliverable_filename is not None

    def get_proposals_summary(self) -> str:
        """Return a summary of all proposals across all teams for the buyer."""
        lines: list[str] = []
        for team in self._teams.values():
            if not team.proposals:
                lines.append(f"{team.team_id}: No proposals submitted.")
                continue
            for p in team.proposals:
                lines.append(
                    f"{p.team_id}: ${p.price} ({p.status.value}) " f"- {p.description[:100]}"
                )
        if not lines:
            return "No proposals have been submitted by any team."
        return "\n".join(lines)

    @property
    def accepted_team(self) -> str | None:
        """Return the accepted team ID, or None if no proposal has been accepted."""
        return self._accepted_team

    def advance_round(self, round_number: int) -> None:
        """Update the current round number."""
        self._current_round = round_number
