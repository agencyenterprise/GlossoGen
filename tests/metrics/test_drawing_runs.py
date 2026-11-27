"""The metrics on a run whose agents sent canvas drawings instead of text.

A drawing is stored as a message with empty text. The size metrics count its
painted pixels and say so in their unit. The metrics that read the words agents
wrote return no measurement, so a canvas run reports them missing rather than
scoring empty texts as zero.
"""

from pathlib import Path

import pytest
import pytest_asyncio

from glossogen.engine.canvas_link import SEND_DRAWING_TOOL
from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from tests.metrics.conftest import METRIC_RUN_GROUP

pytestmark = METRIC_RUN_GROUP

TEAM_A_PIXELS = (3, 2)
TEAM_B_PIXELS = (1,)

TEXT_METRICS = [
    "gzip_compression_ratio",
    "message_entropy",
    "language_repetition",
    "dialog_retransmission",
    "protocol_agreement",
]


def draw(channel_id: str, pixel_count: int) -> list[ToolTurn | SayTurn]:
    """Send one drawing of ``pixel_count`` pixels on ``channel_id``, then stop."""
    pixels = [[x, 0] for x in range(pixel_count)]
    return [
        ToolTurn(
            tool_name=SEND_DRAWING_TOOL,
            args={"channel_id": channel_id, "pixels": pixels, "force": True},
        ),
        SayTurn(text="done"),
    ]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def canvas_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """One round of spot_the_intersection's canvas preset in which every viewer draws once."""
    run_dir = tmp_path_factory.mktemp("canvas-metric-run")
    scenario = build_scenario(
        scenario_name="spot_the_intersection",
        preset_name="knobs_canvas",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
        simulation = await run_simulation(
            scenario=scenario,
            scripts={
                "viewer_a_1": draw(channel_id="link_a", pixel_count=TEAM_A_PIXELS[0]),
                "viewer_a_2": draw(channel_id="link_a", pixel_count=TEAM_A_PIXELS[1]),
                "viewer_b_1": draw(channel_id="link_b", pixel_count=TEAM_B_PIXELS[0]),
                "viewer_b_2": [SayTurn(text="done")],
            },
            tmp_path=run_dir,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
    return MetricRun(
        scenario=scenario, run_dir=run_dir, log_path=simulation.log_path, simulation=simulation
    )


async def test_the_size_metrics_count_pixels(
    canvas_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scored = await score_metrics(
        run=canvas_run,
        metric_names=["mean_chars_per_round", "mean_chars_per_message"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    per_round_a = scored.measurement(metric_name="mean_chars_per_round_team_a")
    assert (per_round_a.score, per_round_a.score_unit) == (
        float(sum(TEAM_A_PIXELS)),
        "pixels/round",
    )
    per_round_b = scored.measurement(metric_name="mean_chars_per_round_team_b")
    assert per_round_b.score == float(sum(TEAM_B_PIXELS))
    per_message_a = scored.measurement(metric_name="mean_chars_per_message_team_a")
    assert (per_message_a.score, per_message_a.score_unit) == (
        sum(TEAM_A_PIXELS) / len(TEAM_A_PIXELS),
        "pixels/message",
    )


async def test_the_text_metrics_do_not_apply(
    canvas_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The judge gets no responses, so a text metric that called it would fail the test."""
    scored = await score_metrics(
        run=canvas_run,
        metric_names=TEXT_METRICS,
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.names() == []
