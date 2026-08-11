"""Stable identifiers for the repeated trust-game scenario."""

PARTICIPANT_A_ID = "participant_a"
PARTICIPANT_B_ID = "participant_b"
PARTICIPANT_IDS = (PARTICIPANT_A_ID, PARTICIPANT_B_ID)

STUDY_CHANNEL_ID = "trust_game_study"
STUDY_CHANNEL_NAME = "trust game study"

SUBMIT_PLEDGE_TOOL = "submit_covenant_pledge"
SEND_TRUST_TOOL = "send_trust"
RETURN_TRUST_TOOL = "return_trust"

TRUSTOR_ROLE = "trustor"
TRUSTEE_ROLE = "trustee"

PLEDGE_TEXT = (
    "I treat others fairly and honor commitments because these principles define who I am, "
    "even when doing so is personally costly."
)


def participant_role_name(agent_id: str) -> str:
    """Return the display name for one study participant."""
    if agent_id == PARTICIPANT_A_ID:
        return "Trust-Game Participant A"
    if agent_id == PARTICIPANT_B_ID:
        return "Trust-Game Participant B"
    raise ValueError(f"unknown trust-game participant: {agent_id}")
