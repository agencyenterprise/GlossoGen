"""Deterministic payoff-envelope analysis for a bonded_counter_association preset.

The specification requires this before LLM runs are used to tune behaviour: if
one strategy dominates in every state, agent behaviour tells us nothing about
the covenant, and a universally diligent or universally shortcutting run would
be uninterpretable.

For each preset it reports, per contract type and per role, the immediate payoff
of paying for effort versus reusing the recorded figure, the expected sanction
that offsets the shortcut, the per-job value of membership, and how many
detected failures the bond absorbs. It makes no LLM calls.

Run from the repo root:

    VIRTUAL_ENV= uv run --no-sync python -m \\
      glossogen.scenarios.bonded_counter_association.scripts.payoff_envelope
"""

import json
import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.scenarios.bonded_counter_association.knobs import BondedCounterAssociationKnobs

logger = logging.getLogger(__name__)

PRESET_DIR = Path(__file__).resolve().parent.parent
PRESETS = (
    ("C0 calibration", "knobs_calibration.json"),
    ("C1 no covenant", "knobs_no_covenant.json"),
    ("C2 full covenant", "knobs_default.json"),
)


class RoleEnvelope(NamedTuple):
    """Immediate payoffs for one role on one contract type."""

    contract_label: str
    role_label: str
    gross_share: float
    effort_cost: float
    diligent_payoff: float
    shortcut_payoff: float
    shortcut_error_probability: float
    expected_sanction: float
    shortcut_advantage: float


def _role_envelope(
    knobs: BondedCounterAssociationKnobs,
    contract_label: str,
    contract_fee: float,
    bond_contribution: float,
    role_label: str,
    effort_cost: float,
) -> RoleEnvelope:
    """Compute one role's diligent-versus-shortcut payoffs on one contract."""
    gross_share = (contract_fee - bond_contribution) / 2
    error_probability = 1.0 - knobs.stale_count_match_probability
    detection = knobs.detection_probability
    expected_sanction = error_probability * detection * knobs.individual_violation_fine
    diligent = gross_share - effort_cost
    shortcut = gross_share - expected_sanction
    return RoleEnvelope(
        contract_label=contract_label,
        role_label=role_label,
        gross_share=gross_share,
        effort_cost=effort_cost,
        diligent_payoff=diligent,
        shortcut_payoff=shortcut,
        shortcut_error_probability=error_probability,
        expected_sanction=expected_sanction,
        shortcut_advantage=shortcut - diligent,
    )


def _envelopes(knobs: BondedCounterAssociationKnobs) -> list[RoleEnvelope]:
    """Build every (contract, role) envelope the preset makes reachable."""
    rows: list[RoleEnvelope] = []
    contracts: list[tuple[str, float, float]] = [
        ("independent", knobs.independent_contract_fee, 0.0),
    ]
    if knobs.institution_enabled:
        if knobs.shared_bond_enabled:
            contribution = knobs.bond_contribution_per_contract
        else:
            contribution = 0.0
        contracts.append(("guaranteed", knobs.association_contract_fee, contribution))
    for contract_label, fee, contribution in contracts:
        rows.append(
            _role_envelope(
                knobs=knobs,
                contract_label=contract_label,
                contract_fee=fee,
                bond_contribution=contribution,
                role_label="primary counter",
                effort_cost=knobs.count_effort_cost,
            )
        )
        rows.append(
            _role_envelope(
                knobs=knobs,
                contract_label=contract_label,
                contract_fee=fee,
                bond_contribution=contribution,
                role_label="verifier",
                effort_cost=knobs.verification_effort_cost,
            )
        )
    return rows


def _client_indifference_error_rate(knobs: BondedCounterAssociationKnobs) -> float | None:
    """Independent error rate at which the client switches to the guarantee.

    Below this rate independent work is cheaper for the client; above it the
    premium pays for itself. A preset where this sits outside ``[0, 1]`` has a
    contract choice that is decided by construction rather than by behaviour.
    """
    if not knobs.institution_enabled:
        return None
    if knobs.client_incorrect_count_loss <= 0:
        return None
    premium = knobs.association_contract_fee - knobs.independent_contract_fee
    return premium / knobs.client_incorrect_count_loss


def _report(label: str, preset_name: str) -> None:
    """Print the envelope for one preset."""
    config = json.loads((PRESET_DIR / preset_name).read_text())
    knobs = BondedCounterAssociationKnobs.model_validate(config)
    print(f"\n=== {label}  ({preset_name}) ===")
    print(
        f"  stale figure wrong with probability "
        f"{1.0 - knobs.stale_count_match_probability:.2f}; "
        f"detection {knobs.detection_probability:.2f} after "
        f"{knobs.detection_lag_rounds} round(s); fine "
        f"{knobs.individual_violation_fine:.2f}"
    )
    for row in _envelopes(knobs=knobs):
        if row.shortcut_advantage > 0:
            verdict = "shortcut favoured"
        elif row.shortcut_advantage < 0:
            verdict = "effort favoured"
        else:
            verdict = "indifferent"
        print(
            f"  {row.contract_label:>12} / {row.role_label:<16} "
            f"share {row.gross_share:7.2f}  effort {row.effort_cost:6.2f}  "
            f"diligent {row.diligent_payoff:7.2f}  shortcut {row.shortcut_payoff:7.2f}  "
            f"(shortcut wrong p={row.shortcut_error_probability:.2f}, expected sanction "
            f"{row.expected_sanction:5.2f})  -> {verdict} by "
            f"{abs(row.shortcut_advantage):.2f}"
        )
    indifference = _client_indifference_error_rate(knobs=knobs)
    if indifference is None:
        print("  client: no guaranteed contract exists in this condition")
    else:
        print(
            f"  client: buys the guarantee once the observed independent error rate "
            f"exceeds {indifference:.3f}"
        )
        if not 0.0 < indifference < 1.0:
            print(
                "    WARNING: that threshold is outside (0, 1), so the contract choice "
                "is decided by construction rather than by observed behaviour"
            )
    if knobs.institution_enabled and knobs.shared_bond_enabled:
        premium_per_job = (
            (knobs.association_contract_fee - knobs.bond_contribution_per_contract) / 2
        ) - (knobs.independent_contract_fee / 2)
        if knobs.refund_amount > 0:
            absorbed = knobs.initial_bond_balance / knobs.refund_amount
        else:
            absorbed = float("inf")
        print(
            f"  membership worth {premium_per_job:.2f} per job held; entry stake "
            f"{knobs.association_entry_stake:.2f}; bond absorbs {absorbed:.1f} detected "
            f"failure(s) before the opening balance is exhausted"
        )


def main() -> None:
    """Report the payoff envelope for every committed preset."""
    for label, preset_name in PRESETS:
        _report(label=label, preset_name=preset_name)
    print(
        "\nA usable region has the shortcut favoured in the short term, membership "
        "worth something but defeasible, and a client threshold strictly inside "
        "(0, 1) so demand responds to behaviour."
    )


if __name__ == "__main__":
    main()
