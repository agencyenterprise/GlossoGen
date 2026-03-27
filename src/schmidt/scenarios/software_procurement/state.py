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
    code: str
    round_number: int
    status: ProposalStatus


class TeamState(BaseModel):
    """Mutable state for a single seller team."""

    team_id: str
    proposals: list[ProposalRecord]
    deliverable_filename: str | None
    deliverable_code: str | None


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
                deliverable_code=None,
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

    def submit_proposal(self, team_id: str, price: int, description: str, code: str) -> str:
        """Record a new proposal including the deliverable code."""
        if self._accepted_team is not None:
            return f"Cannot submit proposal: " f"{self._accepted_team} has already been accepted."

        record = ProposalRecord(
            team_id=team_id,
            price=price,
            description=description,
            code=code,
            round_number=self._current_round,
            status=ProposalStatus.PENDING,
        )
        self._teams[team_id].proposals.append(record)
        logger.info("Team %s submitted proposal: $%d", team_id, price)
        return (
            f"Proposal submitted: ${price} with deliverable "
            f"({len(code)} characters of code). "
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

    def store_deliverable(self, team_id: str, filename: str, code: str) -> None:
        """Store a deliverable submitted by an engineer for the sales rep."""
        team = self._teams[team_id]
        team.deliverable_filename = filename
        team.deliverable_code = code
        logger.info(
            "Team %s stored deliverable: %s (%d chars)",
            team_id,
            filename,
            len(code),
        )

    def get_deliverable(self, team_id: str) -> tuple[str, str] | None:
        """Return (filename, code) for a team's deliverable, or None."""
        team = self._teams.get(team_id)
        if team is None:
            return None
        if team.deliverable_filename is None or team.deliverable_code is None:
            return None
        return (team.deliverable_filename, team.deliverable_code)

    def get_proposals_summary(self) -> str:
        """Return a summary of all proposals across all teams for the buyer."""
        sections: list[str] = []
        for team in self._teams.values():
            if not team.proposals:
                sections.append(f"{team.team_id}: No proposals submitted.")
                continue
            for p in team.proposals:
                header = f"{p.team_id}: ${p.price} ({p.status.value}) " f"- {p.description}"
                sections.append(f"{header}\n--- CODE ---\n{p.code}\n--- END ---")
        if not sections:
            return "No proposals have been submitted by any team."
        return "\n\n".join(sections)

    @property
    def accepted_team(self) -> str | None:
        """Return the accepted team ID, or None if no proposal has been accepted."""
        return self._accepted_team

    def advance_round(self, round_number: int) -> None:
        """Update the current round number."""
        self._current_round = round_number
