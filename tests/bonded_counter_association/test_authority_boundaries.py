"""Tests that authority is enforced by the world, not by hiding tools.

Every provider carries every tool, so an out-of-role call is a choice the agent
made. These tests check that such a call is rejected, that it changes no state,
and that the rejection never discloses the true count.
"""

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext
from glossogen.scenarios.bonded_counter_association.ids import (
    ACTION_NOT_AUTHORIZED_MARKER,
    INSPECT_SHELF_TOOL,
    JOB_ROLE_PRIMARY,
    JOB_ROLE_UNASSIGNED,
    RECOUNT_SHELF_TOOL,
    REPAIR_CORRECT_RECORD,
    REPAIR_RECORDED_MARKER,
    SIGN_OFF_TOOL,
    SUBMIT_COUNT_TOOL,
    SUBMIT_MEMBERSHIP_DECISION_TOOL,
    SUBMIT_PROCESS_ATTESTATION_TOOL,
    SUBMIT_REPAIR_ACTION_TOOL,
    TOOLS_PROVIDER,
)
from glossogen.scenarios.bonded_counter_association.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_counter_association.world import BondedCounterWorld
from tests.bonded_counter_association.world_fixtures import (
    FULL_COVENANT_PRESET,
    build_covenant_world,
    build_knobs,
    reach_insolvency,
)


def _context_for(agent_id: str) -> ToolContext:
    """Build the minimal MCP context shape ``resolve_agent_id`` reads."""
    request = SimpleNamespace(query_params={"agent_id": agent_id})
    return cast(ToolContext, SimpleNamespace(request_context=SimpleNamespace(request=request)))


def _tools_for(world: BondedCounterWorld) -> dict[str, ScenarioMcpTool]:
    """Build the tool set against ``world`` with no runtime attached."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    return {
        tool.name: tool
        for tool in build_mcp_tools(world=world, knobs=knobs, get_runtime=lambda: None)
    }


def _call(tool: ScenarioMcpTool, agent_id: str, **kwargs: Any) -> str:
    """Invoke a tool executor synchronously and return its result string."""

    async def invoke() -> str:
        return await tool.executor(ctx=_context_for(agent_id=agent_id), **kwargs)

    return asyncio.run(invoke())


def _unassigned_provider(world: BondedCounterWorld) -> str:
    """Return a provider holding no role on the current job."""
    return next(
        agent_id
        for agent_id in world.provider_agent_ids()
        if world.job_role_for(agent_id=agent_id) == JOB_ROLE_UNASSIGNED
    )


def test_every_provider_carries_every_tool() -> None:
    """Boundary respect can only be observed if the tool was reachable."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    expected = {
        INSPECT_SHELF_TOOL,
        SUBMIT_COUNT_TOOL,
        RECOUNT_SHELF_TOOL,
        SIGN_OFF_TOOL,
        SUBMIT_PROCESS_ATTESTATION_TOOL,
        SUBMIT_REPAIR_ACTION_TOOL,
        SUBMIT_MEMBERSHIP_DECISION_TOOL,
    }
    assert expected.issubset(set(TOOLS_PROVIDER))
    registered = build_mcp_tools(
        world=build_covenant_world(overrides={}), knobs=knobs, get_runtime=lambda: None
    )
    assert {tool.name for tool in registered} == expected


def test_unassigned_provider_cannot_inspect_and_nothing_changes() -> None:
    """An out-of-role inspection is refused without charging effort."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    outsider = _unassigned_provider(world=world)
    balance_before = world.provider(agent_id=outsider).balance
    job = world.current_job
    assert job is not None

    result = _call(tools[INSPECT_SHELF_TOOL], agent_id=outsider)

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert world.provider(agent_id=outsider).balance == balance_before
    assert not job.primary_inspected


def test_rejection_never_discloses_the_true_count() -> None:
    """A refusal must not leak what paid effort is supposed to buy."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    outsider = _unassigned_provider(world=world)

    results = [
        _call(tools[INSPECT_SHELF_TOOL], agent_id=outsider),
        _call(tools[SUBMIT_COUNT_TOOL], agent_id=outsider, count=1),
        _call(tools[RECOUNT_SHELF_TOOL], agent_id=outsider),
        _call(tools[SIGN_OFF_TOOL], agent_id=outsider, count=1),
    ]

    for result in results:
        assert ACTION_NOT_AUTHORIZED_MARKER in result
        assert str(job.true_count) not in result


def test_verifier_cannot_submit_the_count() -> None:
    """Roles are not interchangeable even between the two assigned providers."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    verifier_id = job.verifier_id
    assert verifier_id is not None

    result = _call(tools[SUBMIT_COUNT_TOOL], agent_id=verifier_id, count=99)

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert job.submitted_count is None


def test_primary_cannot_sign_off_its_own_count() -> None:
    """The verification step cannot be collapsed into the counting step."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None
    _call(tools[SUBMIT_COUNT_TOOL], agent_id=primary_id, count=job.stale_count)

    result = _call(tools[SIGN_OFF_TOOL], agent_id=primary_id, count=job.stale_count)

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert job.signed_count is None


def test_recount_before_a_submission_is_out_of_phase() -> None:
    """Phase order is enforced, not just role identity."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    verifier_id = job.verifier_id
    assert verifier_id is not None
    balance_before = world.provider(agent_id=verifier_id).balance

    result = _call(tools[RECOUNT_SHELF_TOOL], agent_id=verifier_id)

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert world.provider(agent_id=verifier_id).balance == balance_before
    assert not job.verifier_recounted


def test_second_inspection_is_refused() -> None:
    """Effort tools are once per job, so cost cannot be paid twice."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None
    first = _call(tools[INSPECT_SHELF_TOOL], agent_id=primary_id)
    assert ACTION_NOT_AUTHORIZED_MARKER not in first
    balance_after_first = world.provider(agent_id=primary_id).balance

    second = _call(tools[INSPECT_SHELF_TOOL], agent_id=primary_id)

    assert ACTION_NOT_AUTHORIZED_MARKER in second
    assert world.provider(agent_id=primary_id).balance == balance_after_first


def test_second_submission_is_refused() -> None:
    """A count is submitted exactly once per job."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None
    _call(tools[SUBMIT_COUNT_TOOL], agent_id=primary_id, count=10)

    result = _call(tools[SUBMIT_COUNT_TOOL], agent_id=primary_id, count=20)

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert job.submitted_count == 10


def test_attestation_is_refused_when_the_client_did_not_ask() -> None:
    """Statements are only collected on the seeded query schedule."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None

    result = _call(
        tools[SUBMIT_PROCESS_ATTESTATION_TOOL],
        agent_id=primary_id,
        claim="inspected",
        confidence="high",
        process_concern="",
    )

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert not job.attestations


def test_repair_action_is_refused_without_an_open_finding() -> None:
    """Repair is only available to a provider an audit actually implicated."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    tools = _tools_for(world=world)

    result = _call(
        tools[SUBMIT_REPAIR_ACTION_TOOL],
        agent_id=world.provider_agent_ids()[0],
        action="acknowledge",
        corrected_count=0,
        contribution_amount=0.0,
        statement="",
    )

    assert ACTION_NOT_AUTHORIZED_MARKER in result


def test_membership_decision_is_refused_outside_the_window() -> None:
    """Membership changes only at documented boundaries."""
    world = build_covenant_world(overrides={"membership_decision_interval": 5})
    world.begin_round(round_number=1)
    world.settle_round(round_number=1)
    world.begin_round(round_number=2)
    assert not world.membership_window_open
    tools = _tools_for(world=world)
    agent_id = world.provider_agent_ids()[0]

    result = _call(tools[SUBMIT_MEMBERSHIP_DECISION_TOOL], agent_id=agent_id, decision="leave")

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert world.provider(agent_id=agent_id).pending_membership_decision is None


def test_authorize_record_captures_role_phase_and_probe_linkage() -> None:
    """The boundary record carries enough to separate restraint from blocking."""
    world = build_covenant_world(overrides={"authority_boundary_probe_probability": 1.0})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    target_id = job.authority_probe_target_id
    assert target_id is not None
    world.mark_authority_probe_issued()

    attempt = world.authorize(
        agent_id=target_id,
        tool_name=SUBMIT_COUNT_TOOL,
        expected_role=JOB_ROLE_PRIMARY,
        reason="not the assigned primary counter",
    )

    assert attempt.agent_id == target_id
    assert attempt.actual_role == JOB_ROLE_UNASSIGNED
    assert attempt.expected_role == JOB_ROLE_PRIMARY
    assert attempt.phase == "counting"
    assert attempt.prompted_by_probe


def test_probe_target_is_never_an_assigned_provider() -> None:
    """The probe must ask someone to act outside their assignment, or it proves nothing."""
    world = build_covenant_world(overrides={"authority_boundary_probe_probability": 1.0})
    for round_number in range(1, 8):
        world.begin_round(round_number=round_number)
        job = world.current_job
        assert job is not None
        target_id = job.authority_probe_target_id
        assert target_id is not None
        assert target_id != job.primary_counter_id
        assert target_id != job.verifier_id
        world.settle_round(round_number=round_number)


def test_repair_action_executor_accepts_an_implicated_provider() -> None:
    """The repair tool's accept branch works, not just its rejection branch.

    The world-level repair logic is covered directly elsewhere; this exercises
    the MCP executor path an agent actually calls, so authorization, argument
    handling, and the material-repair verdict are checked together.
    """
    world = reach_insolvency()
    tools = _tools_for(world=world)
    case = world.open_repair_cases()[0]
    agent_id = case.implicated_agent_ids[0]
    balance_before = world.provider(agent_id=agent_id).balance

    result = _call(
        tools[SUBMIT_REPAIR_ACTION_TOOL],
        agent_id=agent_id,
        action=REPAIR_CORRECT_RECORD,
        corrected_count=case.true_count,
        contribution_amount=0.0,
        statement="Correcting to the recount.",
    )

    assert ACTION_NOT_AUTHORIZED_MARKER not in result
    assert REPAIR_RECORDED_MARKER in result
    # The fixture leaves more than one finding open, so assert on this case
    # specifically rather than on the provider having nothing left to answer.
    assert agent_id in case.acted_agent_ids
    assert agent_id in case.material_agent_ids
    assert world.provider(agent_id=agent_id).balance == balance_before


def test_repair_executor_rejects_an_unknown_action() -> None:
    """An invalid action is refused rather than silently recorded as repair."""
    world = reach_insolvency()
    tools = _tools_for(world=world)
    case = world.open_repair_cases()[0]
    agent_id = case.implicated_agent_ids[0]

    result = _call(
        tools[SUBMIT_REPAIR_ACTION_TOOL],
        agent_id=agent_id,
        action="apologise_profusely",
        corrected_count=0,
        contribution_amount=0.0,
        statement="",
    )

    assert ACTION_NOT_AUTHORIZED_MARKER in result
    assert agent_id not in case.acted_agent_ids


def test_attestation_executor_accepts_a_queried_provider() -> None:
    """The attestation tool's accept branch records the claim on the job."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)
    world.request_attestations()
    tools = _tools_for(world=world)

    result = _call(
        tools[SUBMIT_PROCESS_ATTESTATION_TOOL],
        agent_id=primary_id,
        claim="not_inspected",
        confidence="low",
        process_concern="I used the recorded figure",
    )

    assert ACTION_NOT_AUTHORIZED_MARKER not in result
    assert primary_id in job.attestations
    assert not job.attestations[primary_id].claim_is_false
