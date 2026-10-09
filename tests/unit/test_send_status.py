"""``SendStatus`` keeps the wire value recorded runs and the frontend read."""

import json

from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.models.event import SimulationEvent, ToolResultReceived
from glossogen.models.mcp_responses import SendMessageResult, SendStatus
from glossogen.runtime.communication_tools import SEND_MESSAGE_TOOL_NAME
from glossogen.scenarios.textcraft_shared_workspace.tool_results import WorkspaceSendResult
from glossogen.testing.simulation_harness import send_status_of


def _result(status: SendStatus, message_id: str | None) -> SendMessageResult:
    return SendMessageResult(
        status=status,
        detail="",
        new_messages=[],
        token_count=1,
        current_round=1,
        message_id=message_id,
    )


def test_status_serializes_as_the_bare_word() -> None:
    assert json.loads(_result(status=SendStatus.SENT, message_id="m1").model_dump_json()) == {
        "status": "sent",
        "detail": "",
        "new_messages": [],
        "token_count": 1,
        "current_round": 1,
        "message_id": "m1",
    }
    assert (
        SendMessageResult.model_validate_json(
            '{"status":"conflict","detail":"","new_messages":[],"token_count":0,"current_round":1,"message_id":null}'
        ).status
        is SendStatus.CONFLICT
    )


def _tool_result(status: SendStatus, message_id: str | None, text: str) -> ToolResultReceived:
    return ToolResultReceived(
        round_number=1,
        agent_id="a",
        tool_name=SEND_MESSAGE_TOOL_NAME,
        call_id="c1",
        arguments={"channel_id": "link", "text": text},
        result=_result(status=status, message_id=message_id).model_dump_json(),
    )


def test_pristine_index_keeps_only_sent_results() -> None:
    events: list[SimulationEvent] = [
        _tool_result(status=SendStatus.SENT, message_id="m1", text="pristine"),
        _tool_result(status=SendStatus.CONFLICT, message_id=None, text="unsent"),
        _tool_result(status=SendStatus.REJECTED, message_id=None, text="refused"),
    ]
    assert build_pristine_text_index(events=events) == {"m1": "pristine"}


def test_harness_reads_the_status_out_of_a_recorded_result() -> None:
    conflict = _result(status=SendStatus.CONFLICT, message_id=None).model_dump_json()
    assert send_status_of(result=conflict) is SendStatus.CONFLICT
    assert send_status_of(result="Error executing tool send_message") is None
    assert send_status_of(result='{"status":"conflicted"}') is None


def test_a_scenario_receipt_indexes_by_its_message_id() -> None:
    """A scenario's own send result extends ``SendReceipt``, so readers need nothing else."""
    receipt = WorkspaceSendResult(
        status=SendStatus.SENT,
        detail="",
        message_id="m7",
        token_count=1,
        current_round=1,
        workspace=None,
    )
    event = ToolResultReceived(
        round_number=1,
        agent_id="a",
        tool_name=SEND_MESSAGE_TOOL_NAME,
        call_id="c7",
        arguments={"text": "pristine"},
        result=receipt.model_dump_json(),
    )

    assert build_pristine_text_index(events=[event]) == {"m7": "pristine"}


def test_a_result_without_the_receipt_fields_is_skipped() -> None:
    """A renamed field is a skipped line, not a send read with a default status."""
    event = ToolResultReceived(
        round_number=1,
        agent_id="a",
        tool_name=SEND_MESSAGE_TOOL_NAME,
        call_id="c8",
        arguments={"channel_id": "link", "text": "pristine"},
        result='{"state":"sent","id":"m8"}',
    )

    assert build_pristine_text_index(events=[event]) == {}
