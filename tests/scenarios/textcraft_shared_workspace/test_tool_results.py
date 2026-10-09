"""textcraft's tool results serialize the platform enums as their bare values."""

import json

from glossogen.models.mcp_responses import SendStatus
from glossogen.runtime.activity_notification import NotificationType
from glossogen.scenarios.textcraft_shared_workspace.events import WorkspaceMessageContextDelivered
from glossogen.scenarios.textcraft_shared_workspace.tool_results import (
    LifecycleEntry,
    WorkspaceSendResult,
    WorkspaceWake,
)


def test_lifecycle_done_serializes_as_done() -> None:
    wake = WorkspaceWake(
        type="done",
        wake_reasons=["done"],
        round=2,
        waited_seconds=0.0,
        workspace=None,
        lifecycle=[LifecycleEntry(type=NotificationType.DONE, text=None, reason="over")],
    )
    payload = json.loads(json.dumps(wake.model_dump()))
    assert payload["lifecycle"] == [{"type": "done", "text": None, "reason": "over"}]


def test_send_result_serializes_its_status() -> None:
    result = WorkspaceSendResult(
        status=SendStatus.REJECTED,
        detail="Round closed.",
        message_id=None,
        token_count=0,
        current_round=1,
        workspace=None,
    )
    assert json.loads(json.dumps(result.model_dump()))["status"] == "rejected"


def test_delivery_carrier_is_shared_with_the_event() -> None:
    event = WorkspaceMessageContextDelivered(
        round_number=1,
        agent_id="crafter_1",
        channel_id="workspace",
        delivery_carrier="wake",
        message_ids=[],
    )
    assert '"delivery_carrier":"wake"' in event.model_dump_json()
