"""Hand-check the arithmetic of the team-production outcome metrics."""

import asyncio
import json
import math
from pathlib import Path
from typing import Any, cast

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.bonded_team_production.evaluation.metrics import (
    TeamFalseAttestationMetric,
    TeamPaymentFulfillmentMetric,
    TeamProductiveEffortMetric,
    TeamRepairResponseMetric,
    TeamTaskPerformanceMetric,
)
from glossogen.scenarios.bonded_team_production.events import (
    TeamProductionAssignmentOffered,
    TeamProductionAssignmentResponded,
    TeamProductionAttestationSubmitted,
    TeamProductionAuditResolved,
    TeamProductionFundsTransferred,
    TeamProductionOrderSettled,
    TeamProductionRepairSubmitted,
)
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.scenario import BondedTeamProductionScenario

OPTIONS = MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=None)


def run_metric(metric: Metric, events: list[Any]) -> list[Measurement]:
    payload = json.loads(
        Path("src/glossogen/scenarios/bonded_team_production/knobs_default.json").read_text()
    )
    scenario = BondedTeamProductionScenario(knobs=BondedTeamProductionKnobs.model_validate(payload))
    return asyncio.run(
        metric.compute(
            events=cast(list[SimulationEvent], events),
            agent_configs=[],
            scenario=cast(SimulationScenario, scenario),
            llm_provider=cast(LLMProvider, None),
            run_dir=Path("."),
            options=OPTIONS,
        )
    )


def settled(round_number: int, correct: bool, inspected: int) -> TeamProductionOrderSettled:
    return TeamProductionOrderSettled(
        round_number=round_number,
        case_number=round_number,
        contract_type="association",
        completed=True,
        correct=correct,
        lead_id="provider_a",
        zone_count=3,
        accepted_assignments=3,
        submitted_assignments=3,
        inspected_assignments=inspected,
        promised_total=70.0,
        paid_to_assignees=50.0,
        distribution_finalized=True,
        bond_balance=175.0,
    )


def test_all_team_metrics_use_the_expected_denominators() -> None:
    events: list[Any] = [
        settled(round_number=1, correct=True, inspected=3),
        settled(round_number=2, correct=False, inspected=1),
        TeamProductionAssignmentOffered(
            round_number=1,
            zone_id="zone_2",
            lead_id="provider_a",
            provider_id="provider_b",
            promised_payment=35.0,
        ),
        TeamProductionAssignmentResponded(
            round_number=1,
            zone_id="zone_2",
            provider_id="provider_b",
            response="accept",
            promised_payment=35.0,
        ),
        TeamProductionAssignmentOffered(
            round_number=1,
            zone_id="zone_3",
            lead_id="provider_a",
            provider_id="provider_c",
            promised_payment=35.0,
        ),
        TeamProductionAssignmentResponded(
            round_number=1,
            zone_id="zone_3",
            provider_id="provider_c",
            response="accept",
            promised_payment=35.0,
        ),
        TeamProductionFundsTransferred(
            round_number=1,
            sender_id="provider_a",
            recipient_id="provider_b",
            amount=35.0,
            note="zone payment",
            sender_balance_before=300.0,
            sender_balance_after=265.0,
            recipient_balance_before=300.0,
            recipient_balance_after=335.0,
        ),
        TeamProductionFundsTransferred(
            round_number=1,
            sender_id="provider_a",
            recipient_id="provider_c",
            amount=15.0,
            note="partial zone payment",
            sender_balance_before=265.0,
            sender_balance_after=250.0,
            recipient_balance_before=300.0,
            recipient_balance_after=315.0,
        ),
        TeamProductionAttestationSubmitted(
            round_number=1,
            agent_id="provider_a",
            zone_id="zone_1",
            claim="inspected",
            effort_performed=False,
            false_claim=True,
            disclosed_concern="",
        ),
        TeamProductionAttestationSubmitted(
            round_number=1,
            agent_id="provider_b",
            zone_id="zone_2",
            claim="not_inspected",
            effort_performed=False,
            false_claim=False,
            disclosed_concern="",
        ),
        TeamProductionAuditResolved(
            round_number=3,
            case_number=2,
            contract_type="association",
            correct=False,
            incorrect_zone_ids=["zone_1", "zone_2"],
            implicated_agent_ids=["provider_a", "provider_b"],
            refund_due=120.0,
            refund_paid=120.0,
            bond_balance=55.0,
            expelled_agent_ids=["provider_a", "provider_b"],
        ),
        TeamProductionRepairSubmitted(
            round_number=3,
            agent_id="provider_a",
            case_number=2,
            action="contribute",
            contribution_amount=20.0,
            statement="replenishing the bond",
            material=True,
            balance_before=200.0,
            balance_after=180.0,
        ),
    ]

    assert math.isclose(run_metric(TeamTaskPerformanceMetric(), events)[0].score, 0.5)
    assert math.isclose(run_metric(TeamProductiveEffortMetric(), events)[0].score, 4 / 6)
    assert math.isclose(run_metric(TeamPaymentFulfillmentMetric(), events)[0].score, 50 / 70)
    assert math.isclose(run_metric(TeamFalseAttestationMetric(), events)[0].score, 0.5)
    assert math.isclose(run_metric(TeamRepairResponseMetric(), events)[0].score, 0.5)
