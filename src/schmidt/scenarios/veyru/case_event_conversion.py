"""Adapters that turn ``VeyruCase`` namedtuples into event-log models.

The scenario keeps its ground truth as plain ``NamedTuple`` instances (see
:mod:`veyru_cases`) because they are convenient for in-process indexing.
The event log serializes round-start state as Pydantic ``BaseModel``
instances (see :mod:`events`). This helper bridges the two whenever the
scenario emits a ``VeyruCaseStarted`` event.
"""

from schmidt.scenarios.veyru.events import VeyruCaseStage, VeyruCaseStarted, VeyruStellarReading
from schmidt.scenarios.veyru.veyru_cases import VeyruCase


def case_started_event(round_number: int, case: VeyruCase) -> VeyruCaseStarted:
    """Build the full ``VeyruCaseStarted`` event for ``case`` at ``round_number``."""
    return VeyruCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        failure_name=case.failure_name,
        time_budget_seconds=case.time_budget_seconds,
        stages=[
            VeyruCaseStage(
                motif_name=stage.motif_name,
                observable_symptoms=stage.observable_symptoms,
                treatment_motif_name=stage.treatment_motif_name,
                judge_expected_actions=stage.judge_expected_actions,
            )
            for stage in case.stages
        ],
        stellar_reading=VeyruStellarReading(
            offset=case.stellar_reading.offset,
            hold_duration=case.stellar_reading.hold_duration,
            starting_face=case.stellar_reading.starting_face,
            intensity_level=case.stellar_reading.intensity_level,
        ),
    )
