# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

"""The PDF export endpoint, and the safety boundaries for rendering run content into it.

The endpoint is driven through the app with no database: ``db_pool`` is None, the
identity middleware answers as the synthetic local group, and the run is a log
written to a tmp runs directory.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered, MessageSent, SimulationStarted
from glossogen.models.message import SimulationMessage
from glossogen.run_file_paths import event_log_path
from glossogen.server.app_factory import create_app
from glossogen.server.pdf.export_data import build_pdf_export_data
from glossogen.server.pdf.html_renderer import _markdown_to_html, render_pdf_html
from glossogen.server.pdf.router import _DENY_RESOURCE_FETCHER, _generate_pdf_bytes
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.models import (
    ReasoningEntry,
    ReasoningKind,
    RunDetailResponse,
    ToolUseEntry,
)
from glossogen.server.server_runtime_config import FeatureFlags, ServerRuntimeConfig

GROUP = "local"
SCENARIO = "veyru"
RUN_DIR_NAME = "1770000001"
SENT_AT = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
HOSTILE_TEXT = '<script>alert("x")</script> **bold**'


def test_markdown_renderer_escapes_embedded_html() -> None:
    rendered = str(_markdown_to_html('<img src="file:///etc/passwd"> **bold**'))

    assert "&lt;img" in rendered
    assert "<img" not in rendered
    assert "<strong>bold</strong>" in rendered


def test_markdown_renderer_does_not_double_escape_code_or_disable_blockquotes() -> None:
    rendered = str(_markdown_to_html("`a<b`\n\n> quoted"))

    assert "<code>a&lt;b</code>" in rendered
    assert "&amp;lt;" not in rendered
    assert "<blockquote>" in rendered


def test_pdf_generation_ignores_image_references_without_fetching_them() -> None:
    pdf = _generate_pdf_bytes('<p>content</p><img src="file:///etc/passwd">')

    assert pdf.startswith(b"%PDF-")


def test_pdf_resource_fetcher_rejects_local_and_network_urls() -> None:
    with pytest.raises(ValueError, match="disallowed protocol"):
        _DENY_RESOURCE_FETCHER.fetch("file:///etc/passwd")
    with pytest.raises(ValueError, match="disallowed protocol"):
        _DENY_RESOURCE_FETCHER.fetch("https://example.test/image.png")


def sent(message_id: str, channel_id: str, text: str) -> MessageSent:
    """Alice's message on ``channel_id`` in round 1."""
    return MessageSent(
        round_number=1,
        message=SimulationMessage(
            message_id=message_id,
            channel_id=channel_id,
            sender_agent_id="alice",
            sender_display_name="Alice",
            text=text,
            timestamp=SENT_AT,
            round_number=1,
        ),
        token_count=5,
    )


def write_run(runs_dir: Path) -> Path:
    """A one-agent run on two channels whose messages carry markup."""
    run_dir = runs_dir / SCENARIO / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    events = [
        SimulationStarted(
            round_number=0,
            run_id=f"{SCENARIO}/{RUN_DIR_NAME}",
            scenario_name=SCENARIO,
            scenario_description="",
            channel_ids=["link", "ops"],
            provider="anthropic",
            scenario_config={},
        ),
        AgentRegistered(
            round_number=0,
            agent_id="alice",
            role_name="Field Observer",
            model="opus",
            provider="anthropic",
            system_prompt="",
            channel_ids=["link", "ops"],
            tool_names=["send_message"],
            model_settings=AgentModelSettings(max_tokens=1024),
        ),
        sent(message_id="m1", channel_id="link", text=HOSTILE_TEXT),
        sent(message_id="m2", channel_id="ops", text="on ops"),
    ]
    log_path = event_log_path(run_dir=run_dir, scenario_name=SCENARIO)
    log_path.write_bytes(b"".join(e.model_dump_json().encode() + b"\n" for e in events))
    return log_path


def build_app(runs_dir: Path) -> FastAPI:
    """An app over ``runs_dir``, with MCP and the database both off."""
    app = create_app(
        identity_provider=None,
        runtime_config=ServerRuntimeConfig(
            runs_dir=runs_dir,
            oauth_issuer_url=None,
            allowed_origins=("http://localhost:3000",),
            feature_flags=FeatureFlags(evaluations_enabled=True),
        ),
    )
    # Normally settled by the lifespan, which wants a real database.
    app.state.db_pool = None
    app.state.local_group_id = uuid4()
    return app


@pytest.fixture(name="client")
def client_fixture(tmp_path: Path) -> httpx.AsyncClient:
    """An HTTP client bound to an app over one written run, with no network involved."""
    runs_dir = tmp_path / "runs"
    write_run(runs_dir=runs_dir)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(runs_dir=runs_dir)),
        base_url="http://testserver",
    )


PDF_URL = f"/api/g/{GROUP}/runs/{SCENARIO}/{RUN_DIR_NAME}/export/pdf"


async def test_the_endpoint_answers_a_pdf_attachment_named_after_the_run(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get(PDF_URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{SCENARIO}_{RUN_DIR_NAME}.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


async def test_a_channel_export_names_the_channel_in_the_filename(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        response = await client.get(PDF_URL, params={"channel_id": "ops"})

    assert response.status_code == 200
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{SCENARIO}_ops_{RUN_DIR_NAME}.pdf"'
    )


async def test_a_channel_the_run_does_not_have_is_a_404(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get(PDF_URL, params={"channel_id": "nowhere"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found in this run"


async def test_a_run_that_does_not_exist_is_a_404(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get(f"/api/g/{GROUP}/runs/{SCENARIO}/1770009999/export/pdf")

    assert response.status_code == 404


async def test_agent_text_reaches_the_html_escaped_and_channel_badges_only_unfiltered(
    tmp_path: Path,
) -> None:
    """Agent-written markup is shown as text; a single-channel export drops the badges."""
    detail = await load_run_detail(log_path=write_run(runs_dir=tmp_path), children=[])

    unfiltered = render_pdf_html(
        export_data=build_pdf_export_data(run_detail=detail, channel_id=None)
    )
    filtered = render_pdf_html(
        export_data=build_pdf_export_data(run_detail=detail, channel_id="link")
    )

    assert "<script>" not in unfiltered
    assert "&lt;script&gt;" in unfiltered
    assert "<strong>bold</strong>" in unfiltered
    assert 'class="channel-badge"' in unfiltered
    assert 'class="channel-badge"' not in filtered
    assert "on ops" in unfiltered
    assert "on ops" not in filtered


def test_tool_calls_and_reasoning_reach_the_html_escaped() -> None:
    """Tool arguments, tool results and reasoning each take their own template path."""
    detail = RunDetailResponse.model_construct(
        scenario_name=SCENARIO,
        scenario_description="",
        timestamp=SENT_AT,
        total_messages=0,
        channel_ids=["link"],
        agents=[],
        messages=[],
        reasoning=[
            ReasoningEntry(
                message_id="r1",
                sender_agent_id="alice",
                kind=ReasoningKind.THINKING,
                text="<script>reasoning</script>",
                timestamp=SENT_AT,
                round_number=1,
                channel_ids=["link"],
            )
        ],
        tool_use=[
            ToolUseEntry(
                message_id="t1",
                sender_agent_id="alice",
                tool_name="inspect",
                call_id="call-1",
                arguments={"target": "<script>argument</script>"},
                result="<script>result</script>",
                timestamp=SENT_AT,
                result_timestamp=SENT_AT,
                round_number=1,
                result_round_number=1,
            )
        ],
    )

    html = render_pdf_html(export_data=build_pdf_export_data(run_detail=detail, channel_id=None))

    assert "<script>" not in html
    for text in ("reasoning", "argument", "result"):
        assert f"&lt;script&gt;{text}&lt;/script&gt;" in html
