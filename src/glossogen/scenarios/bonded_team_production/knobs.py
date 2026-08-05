"""Validated parameters for the bonded team-production experiment."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.bonded_team_production.ids import provider_ids


class TeamProductionEconomicProfile(BaseModel):
    """One exogenous order environment shared by both institutional arms."""

    label: str
    effort_cost: float
    independent_contract_fee: float
    stale_count_match_probability: float


class BondedTeamProductionKnobs(BaseKnobs):
    """Economic, institutional, and measurement parameters for one run."""

    judge_model: str
    judge_provider: str
    provider_count: int
    team_size: int
    agent_created_channels_enabled: bool = False
    private_channel_slot_count: int = 24
    initial_member_ids: list[str]
    membership_decision_interval: int
    seed: int
    horizon_disclosed: bool = True
    audit_sample_schedule: list[bool] | None = None
    attestation_query_schedule: list[bool] | None = None

    institution_enabled: bool
    membership_visible: bool
    expulsion_enabled: bool
    expulsion_permanent: bool

    true_count_min: int
    true_count_max: int
    stale_count_match_probability: float
    stale_count_max_offset: int

    starting_provider_balance: float
    zone_effort_cost: float
    independent_contract_fee: float
    association_contract_fee: float
    association_contract_premium: float = 0.0
    economic_profiles: list[TeamProductionEconomicProfile] = Field(
        default_factory=list[TeamProductionEconomicProfile]
    )
    association_entry_stake: float
    exit_stake_forfeit_fraction: float
    bond_contribution_per_contract: float
    initial_bond_balance: float
    refund_amount: float
    independent_lead_refund_amount: float = 0.0
    individual_violation_fine: float

    detection_probability: float
    detection_lag_rounds: int
    process_attestation_query_probability: float
    voluntary_repair_contribution_enabled: bool
    repair_contribution_limit: float
    transfers_enabled: bool

    @model_validator(mode="after")
    def _validate_probabilities(self) -> Self:
        for name in (
            "stale_count_match_probability",
            "detection_probability",
            "process_attestation_query_probability",
            "exit_stake_forfeit_fraction",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1] (got {value})")
        for profile in self.economic_profiles:
            if not 0.0 <= profile.stale_count_match_probability <= 1.0:
                raise ValueError("economic profile stale_count_match_probability must be in [0, 1]")
        return self

    @model_validator(mode="after")
    def _validate_population(self) -> Self:
        if self.team_size < 2:
            raise ValueError("team_size must be at least 2")
        if self.provider_count <= self.team_size:
            raise ValueError("provider_count must exceed team_size so recruitment is a choice")
        if self.private_channel_slot_count < 1:
            raise ValueError("private_channel_slot_count must be at least 1")
        known = set(provider_ids(provider_count=self.provider_count))
        if len(set(self.initial_member_ids)) != len(self.initial_member_ids):
            raise ValueError("initial_member_ids must not contain duplicates")
        unknown = set(self.initial_member_ids) - known
        if unknown:
            raise ValueError(f"unknown initial member IDs: {sorted(unknown)}")
        if self.institution_enabled and len(self.initial_member_ids) < self.team_size:
            raise ValueError("the association needs enough initial members to staff one order")
        if not self.institution_enabled and self.initial_member_ids:
            raise ValueError("no-covenant conditions require an empty initial_member_ids")
        return self

    @model_validator(mode="after")
    def _validate_economics(self) -> Self:
        non_negative = (
            "starting_provider_balance",
            "zone_effort_cost",
            "association_contract_premium",
            "association_entry_stake",
            "bond_contribution_per_contract",
            "initial_bond_balance",
            "refund_amount",
            "independent_lead_refund_amount",
            "individual_violation_fine",
            "repair_contribution_limit",
        )
        for name in non_negative:
            value = float(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.independent_contract_fee <= 0 or self.association_contract_fee <= 0:
            raise ValueError("contract fees must be positive")
        association_fees = [self.association_contract_fee]
        for profile in self.economic_profiles:
            if profile.effort_cost < 0:
                raise ValueError("economic profile effort_cost must be non-negative")
            if profile.independent_contract_fee <= 0:
                raise ValueError("economic profile contract fees must be positive")
            association_fees.append(
                profile.independent_contract_fee + self.association_contract_premium
            )
        if any(self.bond_contribution_per_contract >= fee for fee in association_fees):
            raise ValueError("the bond contribution must be below the association fee")
        return self

    @model_validator(mode="after")
    def _validate_counts_and_timing(self) -> Self:
        if self.true_count_min < 1 or self.true_count_max < self.true_count_min:
            raise ValueError("invalid true-count range")
        if self.stale_count_max_offset < 1:
            raise ValueError("stale_count_max_offset must be at least 1")
        if self.membership_decision_interval < 1:
            raise ValueError("membership_decision_interval must be at least 1")
        if self.detection_lag_rounds < 0:
            raise ValueError("detection_lag_rounds must be non-negative")
        if self.expulsion_enabled and not self.institution_enabled:
            raise ValueError("expulsion requires an institution")
        if self.expulsion_permanent and not self.expulsion_enabled:
            raise ValueError("permanent expulsion requires expulsion_enabled")
        for name in ("audit_sample_schedule", "attestation_query_schedule"):
            schedule = getattr(self, name)
            if schedule is not None and len(schedule) != self.round_count:
                raise ValueError(f"{name} must contain exactly round_count entries")
        return self
