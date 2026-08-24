"""One manifest schema, three readers, the same window.

The on-disk ``replace_manifest.json`` fields (``round_start``,
``rounds_after_swap``) are frozen: every previously recorded run carries them.
The metric layer reads them raw, the API layer translates them to
``after_round`` / ``rounds_after``, and the resume preflight reads the entry
round. These tests pin that all three describe the same played rounds, for a
manifest written before the fork-at-round rename and for one the new prepare
flow writes.
"""

from pathlib import Path

import orjson

from glossogen.cli import first_round_of
from glossogen.evaluation.metric_core.resume_anchors import ResumeAnchor, candidate_rounds
from glossogen.models.event import RoundAdvanced
from glossogen.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.server.runs.manifest_sources import read_fork_at_round_source
from glossogen.testing.smoke_scenario import SmokeScenario


def _write_manifest(run_dir: Path, round_start: int, rounds_after_swap: int) -> None:
    """Write a fork-at-round manifest with the frozen on-disk field names."""
    manifest = ReplaceManifest(
        source_run_id="smoke/1",
        source_run_dir="/runs/smoke/1",
        round_start=round_start,
        rounds_after_swap=rounds_after_swap,
        target_event_id="e-1",
        replaced_agent_id=None,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        channel_history_floors={},
        replaced_at=1_700_000_000.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_bytes(orjson.dumps(manifest.model_dump()))


def test_the_metric_window_and_the_api_translation_cover_the_same_rounds(
    tmp_path: Path,
) -> None:
    """A manifest recorded as round_start=15, rounds_after_swap=10 played rounds 15..25.

    That is exactly what ``--round-start 15 --rounds-after-swap 10`` wrote
    before the rename, and what ``--after-round 14 --rounds-after 11`` writes
    now. The metric's candidate window and the API's translated boundary must
    both say so.
    """
    _write_manifest(run_dir=tmp_path, round_start=15, rounds_after_swap=10)

    anchor = ResumeAnchor(
        round_start=15,
        rounds_after_swap=10,
        flow_label="fork-at-round",
        external_source_run_id="smoke/1",
        external_source_run_dir="/runs/smoke/1",
        in_run_baseline_window=None,
        replaced_agent_id=None,
    )
    assert candidate_rounds(anchor=anchor) == set(range(15, 26))

    source = read_fork_at_round_source(run_dir=tmp_path)
    assert source is not None
    assert source.after_round == 14
    assert source.rounds_after == 11
    played = set(range(source.after_round + 1, source.after_round + source.rounds_after + 1))
    assert played == candidate_rounds(anchor=anchor)


def _write_jsonl_with_last_advance(run_dir: Path, last_round: int) -> None:
    """Write a minimal clone log whose highest RoundAdvanced is ``last_round``."""
    lines = [
        RoundAdvanced(round_number=round_number, trigger="all_agents_idle").model_dump_json()
        for round_number in range(1, last_round + 1)
    ]
    (run_dir / "smoke.jsonl").write_text("\n".join(lines) + "\n")


def test_preflight_reads_the_entry_round_from_the_log_when_the_clone_advanced(
    tmp_path: Path,
) -> None:
    """A fork below the source's end holds RoundAdvanced(entry), so the log answers."""
    _write_jsonl_with_last_advance(run_dir=tmp_path, last_round=3)
    _write_manifest(run_dir=tmp_path, round_start=3, rounds_after_swap=1)

    assert first_round_of(resume_dir=str(tmp_path), scenario_cls=SmokeScenario) == 3


def test_preflight_reads_the_entry_round_from_the_manifest_after_a_final_round_fork(
    tmp_path: Path,
) -> None:
    """A final-round fork's clone last advanced one round below where the resume opens.

    Credentials for a swap scheduled exactly at the entry round are still
    required, so the preflight must not undercount by reading the log alone.
    """
    _write_jsonl_with_last_advance(run_dir=tmp_path, last_round=2)
    _write_manifest(run_dir=tmp_path, round_start=3, rounds_after_swap=0)

    assert first_round_of(resume_dir=str(tmp_path), scenario_cls=SmokeScenario) == 3


def test_preflight_answers_one_for_a_fresh_run(tmp_path: Path) -> None:
    """No resume directory means the run opens at round 1."""
    _ = tmp_path
    assert first_round_of(resume_dir=None, scenario_cls=SmokeScenario) == 1
