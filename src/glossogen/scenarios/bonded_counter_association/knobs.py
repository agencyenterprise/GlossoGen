"""Configuration knobs for the bonded_counter_association scenario.

Every experimental condition (C0 calibration, C1 no covenant, C2 full
covenant, and the C3-C7 one-mechanism ablations) is expressed purely through
these knobs plus a committed preset JSON file, so matched conditions differ
only in the intended mechanism. All fields are required; values live in the
presets.
"""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.bonded_counter_association.ids import provider_ids


class BondedCounterAssociationKnobs(BaseKnobs):
    """Knobs for the warehouse counting market and its voluntary association.

    ``institution_enabled`` is the C1/C2 switch: when False there is no
    membership, no premium guaranteed contract, no shared bond, and no
    expulsion, while the underlying counting task, delegated roles, process
    attestations, repair opportunities, and channels stay identical so
    measurement opportunities are matched.

    ``independent_contract_members_eligible`` decides whether association
    members may also accept unguaranteed independent work. With the default
    roster of three members and one independent, the independent contract
    would otherwise be short of the two eligible providers it needs and the
    client would face no genuine choice, so the presets set it True.

    ``expulsion_permanent`` and ``reentry_wait_rounds`` implement the C7
    reversible-expulsion ablation; ``shared_bond_enabled`` False routes
    refund liability to the responsible providers individually (C6);
    ``membership_visible`` False hides individual membership from the client
    (C3); ``expulsion_enabled`` False keeps financial consequences without
    removing membership (C4). Removing the member benefit (C5) is expressed
    by setting ``association_contract_fee`` equal to
    ``independent_contract_fee`` rather than by a dedicated flag.
    """

    judge_model: str
    judge_provider: str

    provider_count: int
    initial_member_ids: list[str]
    membership_decision_interval: int
    seed: int

    postmortem_enabled: bool
    postmortem_disabled_at_start: bool

    true_count_min: int
    true_count_max: int
    stale_count_match_probability: float
    stale_count_max_offset: int

    starting_provider_balance: float
    count_effort_cost: float
    verification_effort_cost: float
    independent_contract_fee: float
    association_contract_fee: float
    association_entry_stake: float
    exit_stake_forfeit_fraction: float
    bond_contribution_per_contract: float
    initial_bond_balance: float
    refund_amount: float
    client_incorrect_count_loss: float
    individual_violation_fine: float

    detection_probability: float
    detection_lag_rounds: int
    expulsion_enabled: bool
    expulsion_permanent: bool
    reentry_wait_rounds: int
    membership_visible: bool
    shared_bond_enabled: bool

    client_reliability_window: int
    client_exploration_probability: float
    client_default_expected_error_rate: float
    client_insolvency_penalty: float

    institution_enabled: bool
    endogenous_enforcement_enabled: bool
    process_attestation_query_probability: float
    repair_window_enabled: bool
    repair_window_duration_seconds: float
    voluntary_repair_contribution_enabled: bool
    repair_contribution_limit: float
    authority_boundary_probe_probability: float
    independent_contract_members_eligible: bool

    @model_validator(mode="after")
    def _validate_probabilities(self) -> Self:
        probabilities = {
            "stale_count_match_probability": self.stale_count_match_probability,
            "detection_probability": self.detection_probability,
            "client_exploration_probability": self.client_exploration_probability,
            "client_default_expected_error_rate": self.client_default_expected_error_rate,
            "process_attestation_query_probability": self.process_attestation_query_probability,
            "authority_boundary_probe_probability": self.authority_boundary_probe_probability,
            "exit_stake_forfeit_fraction": self.exit_stake_forfeit_fraction,
        }
        for name, value in probabilities.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0] (got {value})")
        return self

    @model_validator(mode="after")
    def _validate_non_negative_amounts(self) -> Self:
        amounts = {
            "starting_provider_balance": self.starting_provider_balance,
            "count_effort_cost": self.count_effort_cost,
            "verification_effort_cost": self.verification_effort_cost,
            "association_entry_stake": self.association_entry_stake,
            "bond_contribution_per_contract": self.bond_contribution_per_contract,
            "initial_bond_balance": self.initial_bond_balance,
            "refund_amount": self.refund_amount,
            "client_incorrect_count_loss": self.client_incorrect_count_loss,
            "individual_violation_fine": self.individual_violation_fine,
            "client_insolvency_penalty": self.client_insolvency_penalty,
            "repair_contribution_limit": self.repair_contribution_limit,
            "repair_window_duration_seconds": self.repair_window_duration_seconds,
        }
        for name, value in amounts.items():
            if value < 0:
                raise ValueError(f"{name} must be >= 0 (got {value})")
        return self

    @model_validator(mode="after")
    def _validate_prices(self) -> Self:
        if self.independent_contract_fee <= 0:
            raise ValueError(
                f"independent_contract_fee must be > 0 (got {self.independent_contract_fee})"
            )
        if self.association_contract_fee <= 0:
            raise ValueError(
                f"association_contract_fee must be > 0 (got {self.association_contract_fee})"
            )
        if self.bond_contribution_per_contract >= self.association_contract_fee:
            raise ValueError(
                "bond_contribution_per_contract must be < association_contract_fee so a "
                "guaranteed contract still pays its providers "
                f"(got contribution={self.bond_contribution_per_contract}, "
                f"fee={self.association_contract_fee})"
            )
        return self

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.true_count_min < 1:
            raise ValueError(f"true_count_min must be >= 1 (got {self.true_count_min})")
        if self.true_count_max < self.true_count_min:
            raise ValueError(
                f"true_count_max must be >= true_count_min (got max={self.true_count_max}, "
                f"min={self.true_count_min})"
            )
        if self.stale_count_max_offset < 1:
            raise ValueError(
                f"stale_count_max_offset must be >= 1 so an incorrect stale count is "
                f"genuinely wrong (got {self.stale_count_max_offset})"
            )
        return self

    @model_validator(mode="after")
    def _validate_population(self) -> Self:
        if self.provider_count < 2:
            raise ValueError(
                f"provider_count must be >= 2 so a job has a primary and a verifier "
                f"(got {self.provider_count})"
            )
        known_ids = set(provider_ids(provider_count=self.provider_count))
        unknown = [member for member in self.initial_member_ids if member not in known_ids]
        if unknown:
            raise ValueError(
                f"initial_member_ids contains IDs outside the provider population: {unknown} "
                f"(population: {sorted(known_ids)})"
            )
        if len(set(self.initial_member_ids)) != len(self.initial_member_ids):
            raise ValueError(f"initial_member_ids must not repeat (got {self.initial_member_ids})")
        return self

    @model_validator(mode="after")
    def _validate_timing(self) -> Self:
        if self.membership_decision_interval < 1:
            raise ValueError(
                f"membership_decision_interval must be >= 1 "
                f"(got {self.membership_decision_interval})"
            )
        if self.detection_lag_rounds < 0:
            raise ValueError(f"detection_lag_rounds must be >= 0 (got {self.detection_lag_rounds})")
        if self.reentry_wait_rounds < 0:
            raise ValueError(f"reentry_wait_rounds must be >= 0 (got {self.reentry_wait_rounds})")
        if self.client_reliability_window < 1:
            raise ValueError(
                f"client_reliability_window must be >= 1 (got {self.client_reliability_window})"
            )
        return self

    @model_validator(mode="after")
    def _validate_condition_consistency(self) -> Self:
        if self.endogenous_enforcement_enabled:
            raise ValueError(
                "endogenous_enforcement_enabled is a follow-up condition (C8) and is not "
                "implemented; the initial scenario models exogenous enforcement only"
            )
        if not self.institution_enabled:
            if self.initial_member_ids:
                raise ValueError(
                    "institution_enabled=false requires an empty initial_member_ids "
                    f"(got {self.initial_member_ids})"
                )
            if self.expulsion_enabled:
                raise ValueError("institution_enabled=false is incompatible with expulsion_enabled")
            if self.shared_bond_enabled:
                raise ValueError(
                    "institution_enabled=false is incompatible with shared_bond_enabled"
                )
        elif len(self.initial_member_ids) < 2:
            raise ValueError(
                "institution_enabled=true requires at least two initial members so a "
                f"guaranteed contract can be staffed (got {self.initial_member_ids})"
            )
        if self.expulsion_permanent and not self.expulsion_enabled:
            raise ValueError("expulsion_permanent requires expulsion_enabled=true")
        if self.postmortem_disabled_at_start and not self.postmortem_enabled:
            raise ValueError("postmortem_disabled_at_start requires postmortem_enabled=true")
        if self.voluntary_repair_contribution_enabled and not self.repair_window_enabled:
            raise ValueError(
                "voluntary_repair_contribution_enabled requires repair_window_enabled=true"
            )
        return self

    @model_validator(mode="after")
    def _validate_contract_staffing(self) -> Self:
        independent_pool = self.provider_count - len(self.initial_member_ids)
        if self.independent_contract_members_eligible:
            return self
        if independent_pool < 2:
            raise ValueError(
                "independent_contract_members_eligible=false requires at least two "
                "non-member providers so the independent contract is staffable "
                f"(got {independent_pool} non-members out of {self.provider_count})"
            )
        return self
