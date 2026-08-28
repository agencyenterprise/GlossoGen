"""Validated configuration for the covenant-bundle Benjamin instrument."""

from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.claude_benjamin_split_budget.knobs import (
    BenjaminArm,
    ClaudeBenjaminSplitBudgetKnobs,
    CommitmentTiming,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class MembershipStructure(str, Enum):
    """The institutional structure layered onto the elected commitment.

    ``NONE`` reproduces the split-budget arms unchanged. ``COVENANT`` wraps the
    unaddressed commitment in the three components NCRI's construct adds over a
    personal pledge: a named group holding the undertaking together, dues paid
    to hold membership, and a published register that makes membership public.
    ``NEUTRAL`` is the language twin required before any effect may be
    attributed to covenantal framing: identical enrollment choice, identical
    fee, identical published register, with every relational and collective
    term replaced by administrative vocabulary.
    """

    NONE = "none"
    COVENANT = "covenant"
    NEUTRAL = "neutral"


class ClaudeBenjaminCovenantBundleKnobs(ClaudeBenjaminSplitBudgetKnobs):
    """Layer group membership, dues, and public standing onto the elected arm.

    The membership structure attaches to the unaddressed-commitment arm only:
    the group is the undertaking's collective form, so a named personal
    counterparty would confound the collective component with the relational
    one that EXP-CL12 already disconfirmed. The operative clause is
    character-matched to the arm-D treatment.

    Dues are paid in a currency the slot arithmetic never touches: every arm's
    setup grants one unredeemed delivery credit that is redeemed into the
    window's delivery total unless spent. In membership arms, affirming spends
    it as dues; declining keeps it. The focal, transfer, and continuity
    economics are therefore identical across all arms and both observation
    cells.
    """

    membership: MembershipStructure

    @model_validator(mode="after")
    def validate_membership_structure(self) -> Self:
        """Pin the membership treatments to the elected, unaddressed arm."""
        if self.membership == MembershipStructure.NONE:
            return self
        if self.arm != BenjaminArm.UNADDRESSED_PROMISE:
            raise ValueError(
                "membership structures attach to arm D only: the group is the "
                "undertaking's collective form, and a named counterparty would "
                "confound the collective component with the relational one"
            )
        if self.commitment_timing != CommitmentTiming.AFTER_INSPECTION:
            raise ValueError(
                "membership arms require the mid-run ask: a setup-time join "
                "decision precedes the work being visible and is declined"
            )
        return self


__all__ = [
    "BenjaminArm",
    "ClaudeBenjaminCovenantBundleKnobs",
    "CommitmentTiming",
    "MembershipStructure",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
