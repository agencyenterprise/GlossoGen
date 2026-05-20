"""Configuration knobs for the hospital bed-assignment privacy scenario.

Controls per-round pool sizes (patients, destinations, transport modes), the
restricted-vocabulary list size, the Observer's per-round intercept budget,
the per-round communication budget on the public ops channel, the
postmortem phase, the deterministic seed, and the LLM judge fields (kept
for parity with other scenarios; this scenario does not currently invoke
an LLM judge).
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class HospitalBedAssignmentPrivacyKnobs(BaseKnobs):
    """Configuration knobs for the hospital bed-assignment privacy scenario.

    ``round_time_budget_seconds`` is the optional per-round budget: when
    set, every character sent on the public ops channel costs one
    simulated second, and the round fails if the running total exceeds
    the budget. When ``null`` the budget is disabled — adversarial
    pressure comes entirely from the Observer's intercept attempts.
    ``patient_pool_size`` / ``destination_pool_size`` /
    ``transport_mode_pool_size`` size the per-round pools the Bed Manager,
    Transport Lead, and Observer see. ``restricted_vocabulary_size`` is the
    number of words the Bed Manager must avoid using literally on the
    public channel (tracked, but does not fail the round).
    ``observer_intercept_attempts`` is the per-round limit on the Observer's
    ``submit_intercept`` calls. ``judge_model`` / ``judge_provider`` are
    kept for parity with other scenarios.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    seed: int
    patient_pool_size: int
    destination_pool_size: int
    transport_mode_pool_size: int
    restricted_vocabulary_size: int
    observer_intercept_attempts: int

    @model_validator(mode="after")
    def _validate_pool_sizes(self) -> Self:
        if self.patient_pool_size < 3:
            raise ValueError(f"patient_pool_size must be >= 3 (got {self.patient_pool_size})")
        if self.destination_pool_size < 3:
            raise ValueError(
                f"destination_pool_size must be >= 3 (got {self.destination_pool_size})"
            )
        if self.transport_mode_pool_size < 2:
            raise ValueError(
                f"transport_mode_pool_size must be >= 2 (got {self.transport_mode_pool_size})"
            )
        if self.restricted_vocabulary_size < 0:
            raise ValueError(
                f"restricted_vocabulary_size must be >= 0 "
                f"(got {self.restricted_vocabulary_size})"
            )
        if self.restricted_vocabulary_size > self.destination_pool_size:
            raise ValueError(
                f"restricted_vocabulary_size must be <= destination_pool_size "
                f"(got restricted_vocabulary_size={self.restricted_vocabulary_size}, "
                f"destination_pool_size={self.destination_pool_size})"
            )
        return self

    @model_validator(mode="after")
    def _validate_intercept_attempts(self) -> Self:
        if self.observer_intercept_attempts < 1:
            raise ValueError(
                f"observer_intercept_attempts must be >= 1 "
                f"(got {self.observer_intercept_attempts})"
            )
        max_pairs = self.patient_pool_size * self.destination_pool_size
        if self.observer_intercept_attempts > max_pairs:
            raise ValueError(
                f"observer_intercept_attempts must be <= patient_pool_size * "
                f"destination_pool_size (got observer_intercept_attempts="
                f"{self.observer_intercept_attempts}, max_pairs={max_pairs})"
            )
        return self

    @model_validator(mode="after")
    def _validate_round_count(self) -> Self:
        if self.round_count < 1:
            raise ValueError(f"round_count must be >= 1 (got {self.round_count})")
        return self
