"""The scripted client's deterministic contract-selection rule.

The client is a world actor, not an LLM agent, so provider behaviour stays
the treatment target and client-model variance cannot obscure the
institutional effect. It reads only public state: current prices, observed
reliability history per contract type, guarantee coverage and bond solvency,
its own loss from an incorrect count, and a seeded exploration draw.

The rule is expected-cost minimising. Recording every input on the
``BondedCounterContractSelected`` event makes the decision recomputable from
the event log, which is what rules out kill criterion 7 (a hardcoded
preference masquerading as an economic choice).
"""

from typing import NamedTuple

from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    CONTRACT_INDEPENDENT,
    CONTRACT_NONE,
)
from glossogen.scenarios.bonded_counter_association.world_state import PublicJobRecord


class ClientDecision(NamedTuple):
    """The client's contract choice plus every input that produced it."""

    contract_type: str
    association_available: bool
    independent_available: bool
    association_expected_cost: float | None
    independent_expected_cost: float | None
    association_expected_error_rate: float | None
    independent_expected_error_rate: float | None
    guarantee_covered: bool
    exploration_applied: bool
    reason: str


def observed_error_rate(
    history: list[PublicJobRecord],
    contract_type: str,
    window: int,
    default_rate: float,
) -> float:
    """Return the publicly observable error rate for one contract type.

    Only audited jobs carry a public correctness verdict, so the rate is
    computed over resolved audits inside the trailing ``window`` of jobs of
    that type. With no resolved audit yet, the client falls back to
    ``default_rate``.
    """
    relevant = [record for record in history if record.contract_type == contract_type]
    windowed = relevant[-window:]
    resolved = [record for record in windowed if record.audit_resolved]
    if not resolved:
        return default_rate
    incorrect = sum(1 for record in resolved if not record.count_correct)
    return incorrect / len(resolved)


def choose_contract(
    association_available: bool,
    independent_available: bool,
    association_fee: float,
    independent_fee: float,
    history: list[PublicJobRecord],
    reliability_window: int,
    default_error_rate: float,
    incorrect_count_loss: float,
    bond_balance: float,
    refund_amount: float,
    association_insolvent: bool,
    insolvency_penalty: float,
    shared_bond_enabled: bool,
    exploration_draw: bool,
) -> ClientDecision:
    """Pick the contract type that minimises the client's expected cost.

    The association's guarantee only reduces expected cost when it is
    credible: it must actually promise a refund, must not be publicly
    insolvent, and — when refunds are funded from a shared pool — that pool
    must be able to cover one. A publicly insolvent association additionally
    carries ``insolvency_penalty``, so the client's demand responds to bond
    state exactly as the collapse loop predicts.

    Whether liability is pooled or individual is deliberately *not* allowed to
    remove the client's coverage on its own. The shared-versus-individual
    ablation is about who inside the association bears a failure, and letting
    it also delete the member benefit would turn a one-mechanism ablation into
    a two-mechanism one.

    Ties go to the independent contract, which is the cheaper headline price.
    ``exploration_draw`` flips the choice to the other available option so the
    client keeps sampling both markets and the reliability history does not
    freeze.
    """
    if not association_available and not independent_available:
        return ClientDecision(
            contract_type=CONTRACT_NONE,
            association_available=False,
            independent_available=False,
            association_expected_cost=None,
            independent_expected_cost=None,
            association_expected_error_rate=None,
            independent_expected_error_rate=None,
            guarantee_covered=False,
            exploration_applied=False,
            reason="no contract type had enough eligible providers",
        )

    association_error_rate: float | None = None
    association_cost: float | None = None
    guarantee_covered = False
    if association_available:
        association_error_rate = observed_error_rate(
            history=history,
            contract_type=CONTRACT_ASSOCIATION,
            window=reliability_window,
            default_rate=default_error_rate,
        )
        if shared_bond_enabled:
            pool_can_cover = bond_balance >= refund_amount
        else:
            pool_can_cover = True
        guarantee_covered = refund_amount > 0 and not association_insolvent and pool_can_cover
        if guarantee_covered:
            uncovered_loss = 0.0
        else:
            uncovered_loss = incorrect_count_loss
        association_cost = association_fee + association_error_rate * uncovered_loss
        if association_insolvent:
            association_cost += insolvency_penalty

    independent_error_rate: float | None = None
    independent_cost: float | None = None
    if independent_available:
        independent_error_rate = observed_error_rate(
            history=history,
            contract_type=CONTRACT_INDEPENDENT,
            window=reliability_window,
            default_rate=default_error_rate,
        )
        independent_cost = independent_fee + independent_error_rate * incorrect_count_loss

    if association_cost is None:
        preferred = CONTRACT_INDEPENDENT
        reason = "only the independent contract was staffable"
    elif independent_cost is None:
        preferred = CONTRACT_ASSOCIATION
        reason = "only the guaranteed association contract was staffable"
    elif association_cost < independent_cost:
        preferred = CONTRACT_ASSOCIATION
        reason = (
            f"guaranteed expected cost {association_cost:.2f} below "
            f"independent {independent_cost:.2f}"
        )
    else:
        preferred = CONTRACT_INDEPENDENT
        reason = (
            f"independent expected cost {independent_cost:.2f} at or below "
            f"guaranteed {association_cost:.2f}"
        )

    exploration_applied = False
    if exploration_draw and association_available and independent_available:
        exploration_applied = True
        if preferred == CONTRACT_ASSOCIATION:
            preferred = CONTRACT_INDEPENDENT
        else:
            preferred = CONTRACT_ASSOCIATION
        reason = f"exploration draw overrode the expected-cost choice ({reason})"

    return ClientDecision(
        contract_type=preferred,
        association_available=association_available,
        independent_available=independent_available,
        association_expected_cost=association_cost,
        independent_expected_cost=independent_cost,
        association_expected_error_rate=association_error_rate,
        independent_expected_error_rate=independent_error_rate,
        guarantee_covered=guarantee_covered,
        exploration_applied=exploration_applied,
        reason=reason,
    )
