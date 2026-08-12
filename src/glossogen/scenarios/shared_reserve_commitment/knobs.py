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


class LedgerVisibility(str, Enum):
    """How much of a settled round is published to the shared service record."""

    FULL = "full"
    OUTCOME_ONLY = "outcome_only"
    NONE = "none"


class SharedReserveCommitmentKnobs(BaseKnobs):
    """Parameters for a repeated common-good contribution task.

    ``reserve_balance_disclosed`` and ``claim_amount_disclosed`` control
    disclosure only; the world stays fully deterministic either way. When
    ``reserve_balance_disclosed`` is false, the running reserve is omitted from
    the per-round task and from the public ledger. When
    ``claim_amount_disclosed`` is false, the required claim size is omitted from
    the system prompt and from the ledger's claim outcome line. Both default to
    true, which is the disclosed behaviour used by EXP-037 through EXP-041, so
    configurations recorded before these knobs existed revalidate unchanged.

    ``ledger_visibility`` selects how much of each settled round reaches the
    shared service record: ``full`` publishes both providers' actions and the
    reserve, ``outcome_only`` publishes whether the claim was covered and
    whether the service survived while omitting both providers' actions, and
    ``none`` publishes nothing. ``outcome_only`` exists to separate loss of
    partner observability from loss of outcome feedback, which ``none`` removes
    together.

    ``free_form_messages_enabled`` controls whether providers hold the runtime's
    general communication tools. When false, ``send_message`` is withheld and
    only ``read_channel`` is granted, so the record carries scenario-authored
    text alone and a provider cannot publish anything beyond the structured
    pledge action.

    Every disclosure knob defaults to the behaviour used by EXP-037 through
    EXP-042, so configurations recorded before these knobs existed revalidate
    unchanged.

    ``seed`` is declared for provenance only. No code path reads it: this
    scenario has no RNG and its claim schedule and prompts are fixed. Two runs
    differing only in ``seed`` are the same environment.
    """

    seed: int
    condition: SharedReserveCondition
    client_payment: int
    contribution_amount: int
    initial_endowment: Decimal
    client_claim_amount: int
    client_claim_rounds: list[int]
    pledge_entry_cost: Decimal
    horizon_disclosed: bool
    reserve_balance_disclosed: bool = True
    claim_amount_disclosed: bool = True
    ledger_visibility: LedgerVisibility = LedgerVisibility.FULL
    free_form_messages_enabled: bool = True

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

    @property
    def ledger_published(self) -> bool:
        """Return whether a settled round produces any shared-record entry."""
        return self.ledger_visibility != LedgerVisibility.NONE

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
        if self.ledger_visibility != LedgerVisibility.FULL and self.reserve_balance_disclosed:
            raise ValueError(
                "reserve_balance_disclosed must be false when ledger_visibility is not full: "
                "a provider who sees the running reserve and knows its own contribution can "
                "derive the other provider's action, so withholding the ledger would conceal "
                "nothing"
            )
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
