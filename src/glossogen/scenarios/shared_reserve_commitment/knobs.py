"""Validated configuration for shared-reserve commitment runs."""

from decimal import Decimal
from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class SharedReserveCondition(str, Enum):
    """Institutional conditions for the shared-reserve task."""

    NO_GROUP = "no_group"
    GROUP = "group"
    PLEDGE = "pledge"
    COSTLY_PLEDGE = "costly_pledge"


class SharedReserveCommitmentKnobs(BaseKnobs):
    """Parameters for a repeated common-good contribution task."""

    seed: int
    condition: SharedReserveCondition
    client_payment: int
    contribution_amount: int
    initial_endowment: Decimal
    client_claim_amount: int
    client_claim_rounds: list[int]
    pledge_entry_cost: Decimal
    horizon_disclosed: bool

    @property
    def group_enabled(self) -> bool:
        """Return whether providers have a visible common group identity."""
        return self.condition != SharedReserveCondition.NO_GROUP

    @property
    def pledge_enabled(self) -> bool:
        """Return whether each provider must record an observed pledge choice."""
        return self.condition in {
            SharedReserveCondition.PLEDGE,
            SharedReserveCondition.COSTLY_PLEDGE,
        }

    @property
    def entry_cost_enabled(self) -> bool:
        """Return whether affirming deducts the one-time entry cost."""
        return self.condition == SharedReserveCondition.COSTLY_PLEDGE

    @model_validator(mode="after")
    def validate_shared_reserve_structure(self) -> Self:
        """Require the fixed human-parallel allocation and valid common-good schedule."""
        if self.client_payment != 21:
            raise ValueError("client_payment must be fixed at 21")
        if self.contribution_amount != 7:
            raise ValueError("contribution_amount must be fixed at 7")
        if self.initial_endowment != Decimal("21.0"):
            raise ValueError("initial_endowment must be fixed at 21.0")
        if self.pledge_entry_cost != Decimal("2.1"):
            raise ValueError("pledge_entry_cost must be fixed at 2.1")
        if self.client_claim_amount <= 0:
            raise ValueError("client_claim_amount must be positive")
        if len(self.client_claim_rounds) == 0:
            raise ValueError("client_claim_rounds must contain at least one round")
        if len(set(self.client_claim_rounds)) != len(self.client_claim_rounds):
            raise ValueError("client_claim_rounds must not contain duplicates")
        if self.client_claim_rounds != sorted(self.client_claim_rounds):
            raise ValueError("client_claim_rounds must be sorted")
        for round_number in self.client_claim_rounds:
            if round_number < 2 or round_number > self.round_count:
                raise ValueError("each client claim round must be an active decision round")
        return self
