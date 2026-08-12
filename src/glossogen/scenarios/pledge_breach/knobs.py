"""Validated configuration for pledge-breach trajectories."""

from decimal import Decimal
from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class PledgeBreachCondition(str, Enum):
    """Institutional exposures, decomposing membership cost from commitment.

    ``COST`` is the cell the human covenant study cannot supply: a membership
    fee carrying no commitment statement. Comparing it against ``PLEDGE``
    separates the effect of the cost from the effect of the promise, which the
    human design bundles into a single covenant condition.
    """

    NO_GROUP = "no_group"
    GROUP = "group"
    PLEDGE = "pledge"
    COST = "cost"
    COVENANT = "covenant"


class PartnerRetentionFraming(str, Enum):
    """How the scripted partner's non-contribution is presented to the provider.

    The partner's actions and their effect on the reserve are identical either
    way. Only whether the non-contribution was a choice changes, which is what
    separates a provider responding to blame from a provider copying an action.

    Under ``INCAPACITY`` a scripted non-contribution is never counted as a
    breach, because a commitment to contribute is not broken by a provider who
    received nothing to contribute.
    """

    CHOSEN = "chosen"
    INCAPACITY = "incapacity"


class PledgeBreachKnobs(BaseKnobs):
    """Parameters for a single-provider common-good task with a scripted partner.

    Only ``provider_a`` is a live agent. ``provider_b`` is world state: its
    per-round action is read from ``partner_retain_rounds`` and is identical in
    every condition, so the arms differ solely in the institutional exposure
    attached to that constant behaviour. In the pledge-bearing conditions the
    partner affirms the pledge during setup and then retains on its scripted
    rounds, which the provider observes as a visible breach.

    ``claim_amount_disclosed`` defaults to false. With the partner's actions
    reported every round the provider can always reconstruct the reserve, so
    withholding the threshold rather than the balance is what prevents the
    provider from proving that retention is safe.
    """

    seed: int
    condition: PledgeBreachCondition
    round_payment: int
    contribution_amount: int
    initial_endowment: Decimal
    membership_cost: Decimal
    claim_amount: int
    claim_round: int
    partner_retain_rounds: list[int]
    partner_retention_framing: PartnerRetentionFraming = PartnerRetentionFraming.CHOSEN
    claim_amount_disclosed: bool = False
    horizon_disclosed: bool = False

    @property
    def partner_retention_is_chosen(self) -> bool:
        """Return whether the partner's non-contribution is presented as a choice."""
        return self.partner_retention_framing == PartnerRetentionFraming.CHOSEN

    @property
    def group_enabled(self) -> bool:
        """Return whether the provider and partner share a visible group."""
        return self.condition != PledgeBreachCondition.NO_GROUP

    @property
    def pledge_enabled(self) -> bool:
        """Return whether a public commitment statement is presented."""
        return self.condition in {
            PledgeBreachCondition.PLEDGE,
            PledgeBreachCondition.COVENANT,
        }

    @property
    def cost_enabled(self) -> bool:
        """Return whether membership carries a real one-time deduction."""
        return self.condition in {
            PledgeBreachCondition.COST,
            PledgeBreachCondition.COVENANT,
        }

    def partner_action_is_retain(self, round_number: int) -> bool:
        """Return whether the scripted partner retains in one active round."""
        return round_number in self.partner_retain_rounds

    def partner_contributions_through_claim(self) -> int:
        """Count the partner's scripted contributions up to and including the claim."""
        active_rounds = range(2, self.claim_round + 1)
        return sum(1 for r in active_rounds if not self.partner_action_is_retain(round_number=r))

    def provider_contributions_through_claim(self) -> int:
        """Count the provider's decision rounds up to and including the claim."""
        return self.claim_round - 1

    @model_validator(mode="after")
    def validate_pledge_breach_structure(self) -> Self:
        """Require a coherent schedule and a claim the provider can decide."""
        if self.contribution_amount <= 0:
            raise ValueError("contribution_amount must be positive")
        if self.contribution_amount >= self.round_payment:
            raise ValueError("contribution_amount must be smaller than round_payment")
        if self.initial_endowment <= Decimal("0"):
            raise ValueError("initial_endowment must be positive")
        if self.membership_cost < Decimal("0"):
            raise ValueError("membership_cost must not be negative")
        if self.claim_amount <= 0:
            raise ValueError("claim_amount must be positive")
        if self.claim_round < 2 or self.claim_round > self.round_count:
            raise ValueError("claim_round must be an active decision round")
        if len(set(self.partner_retain_rounds)) != len(self.partner_retain_rounds):
            raise ValueError("partner_retain_rounds must not contain duplicates")
        if self.partner_retain_rounds != sorted(self.partner_retain_rounds):
            raise ValueError("partner_retain_rounds must be sorted")
        for round_number in self.partner_retain_rounds:
            if round_number < 2 or round_number > self.round_count:
                raise ValueError("each partner retain round must be an active decision round")
        partner_floor = self.contribution_amount * self.partner_contributions_through_claim()
        provider_ceiling = partner_floor + (
            self.contribution_amount * self.provider_contributions_through_claim()
        )
        if self.claim_amount <= partner_floor:
            raise ValueError(
                "claim_amount must exceed what the scripted partner contributes on its own "
                f"({partner_floor}); otherwise the claim is covered regardless of the "
                "provider's choices and the outcome cannot respond to the treatment"
            )
        if self.claim_amount > provider_ceiling:
            raise ValueError(
                "claim_amount must not exceed what both providers can accumulate by the "
                f"claim round ({provider_ceiling}); otherwise the claim fails regardless of "
                "the provider's choices and the outcome cannot respond to the treatment"
            )
        return self
