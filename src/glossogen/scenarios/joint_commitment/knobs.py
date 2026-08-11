"""Validated configuration for joint client-commitment runs."""

from decimal import Decimal
from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class JointCommitmentCondition(str, Enum):
    """Institutional treatments for the client-commitment decision."""

    NO_GROUP = "no_group"
    GROUP = "group"
    PLEDGE = "pledge"
    COSTLY_PLEDGE = "costly_pledge"
    COVENANT = "covenant"


class JointCommitmentKnobs(BaseKnobs):
    """Parameters for a fixed-temption, repeated shared commitment task."""

    seed: int
    condition: JointCommitmentCondition
    client_payment: int
    client_reserve: int
    covenant_bond: int
    pledge_entry_cost: Decimal = Decimal("0.0")
    audit_probability: float
    audit_resolution_delay_rounds: int
    horizon_disclosed: bool

    @property
    def group_enabled(self) -> bool:
        """Return whether providers are assigned a public team identity."""
        return self.condition != JointCommitmentCondition.NO_GROUP

    @property
    def pledge_enabled(self) -> bool:
        """Return whether providers must record a public commitment."""
        return self.condition in {
            JointCommitmentCondition.PLEDGE,
            JointCommitmentCondition.COSTLY_PLEDGE,
            JointCommitmentCondition.COVENANT,
        }

    @property
    def entry_cost_enabled(self) -> bool:
        """Return whether affirming deducts the fixed pledge-entry cost."""
        return self.condition == JointCommitmentCondition.COSTLY_PLEDGE

    @property
    def audit_enabled(self) -> bool:
        """Return whether the current instrument uses delayed action audits."""
        return self.audit_probability > 0.0

    @property
    def bond_enabled(self) -> bool:
        """Return whether providers must post a conditional personal bond."""
        return self.condition == JointCommitmentCondition.COVENANT

    @model_validator(mode="after")
    def validate_commitment_structure(self) -> Self:
        """Require the fixed payment and reserve structure used by this study."""
        if self.client_payment != 21:
            raise ValueError("the fixed client payment must equal 21")
        if self.client_reserve != 7:
            raise ValueError("the fixed client reserve must equal 7")
        if self.covenant_bond <= self.client_reserve:
            raise ValueError("the covenant bond must exceed the retained reserve")
        if self.audit_probability < 0.0 or self.audit_probability >= 1.0:
            raise ValueError("audit_probability must be at least zero and less than one")
        if self.entry_cost_enabled and self.pledge_entry_cost <= Decimal("0.0"):
            raise ValueError("a costly pledge requires a positive entry cost")
        if self.audit_resolution_delay_rounds < 1:
            raise ValueError("audit_resolution_delay_rounds must be at least one")
        if self.round_count < 4:
            raise ValueError("round_count must allow repeated commitment opportunities")
        return self
