"""Reading summary caches written before the fork-at-round rename.

Every completed run on disk carries a ``run_summary_cache.json`` in whatever
shape the code that finished it used. Invalidating the pre-rename shape would
rescan every previously recorded run's JSONL at once, so the cache reader
translates it instead: ``resume_at_round_source`` becomes
``fork_at_round_source`` and the boundary fields become ``after_round`` /
``rounds_after``. These tests prove the translation by pairing an old-shape
cache with an unparseable JSONL: an answer can only come from the cache.
"""

from pathlib import Path
from typing import Any

import orjson

from glossogen.server.runs.discovery import build_summary


def _legacy_cache(
    replace_agent_source: dict[str, Any] | None,
    resume_at_round_source: dict[str, Any] | None,
) -> dict[str, Any]:
    """A cache in the pre-rename shape, complete with every then-required field."""
    return {
        "scenario_name": "smoke",
        "scenario_description": "cached run",
        "scenario_config": {"round_count": 25},
        "provider": "anthropic",
        "total_messages": 999,
        "total_cost_usd": 1.5,
        "duration_seconds": 60.0,
        "status": "scenario_complete",
        "models": ["claude-sonnet-4-6"],
        "agent_models": [
            {
                "agent_id": "first_agent",
                "role_name": "First Agent",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
            }
        ],
        "current_round": 25,
        "fork_source": None,
        "replace_agent_source": replace_agent_source,
        "cross_run_replace_agent_source": None,
        "resume_at_round_source": resume_at_round_source,
    }


def _write_run(tmp_path: Path, cache: dict[str, Any]) -> Path:
    """Materialize a run dir whose only readable answer is the cache."""
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "smoke.jsonl").write_text("this is not json\n")
    (run_dir / "run_summary_cache.json").write_bytes(orjson.dumps(cache))
    return run_dir


async def test_an_old_fork_cache_translates_without_a_rescan(tmp_path: Path) -> None:
    """round_start=16, rounds_after_resume=10 reads back as after_round=15 (+11)."""
    run_dir = _write_run(
        tmp_path=tmp_path,
        cache=_legacy_cache(
            replace_agent_source=None,
            resume_at_round_source={
                "source_run_id": "smoke/1",
                "round_start": 16,
                "rounds_after_resume": 10,
                "target_event_id": "e-1",
                "resumed_at": "2026-06-15T12:00:00Z",
            },
        ),
    )

    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash=None,
    )

    assert summary is not None
    assert summary.total_messages == 999
    assert summary.fork_at_round_source is not None
    assert summary.fork_at_round_source.after_round == 15
    assert summary.fork_at_round_source.rounds_after == 11
    assert summary.fork_at_round_source.source_run_id == "smoke/1"


async def test_an_old_replace_agent_cache_translates_its_boundary(tmp_path: Path) -> None:
    """The replace source's round_start=15 reads back as after_round=14."""
    run_dir = _write_run(
        tmp_path=tmp_path,
        cache=_legacy_cache(
            replace_agent_source={
                "source_run_id": "smoke/1",
                "round_start": 15,
                "target_event_id": "e-2",
                "replaced_agent_id": "first_agent",
                "replacement_model": "claude-sonnet-4-6",
                "replacement_provider": "anthropic",
                "replaced_at": "2026-06-15T12:00:00Z",
            },
            resume_at_round_source=None,
        ),
    )

    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash=None,
    )

    assert summary is not None
    assert summary.fork_at_round_source is None
    assert summary.replace_agent_source is not None
    assert summary.replace_agent_source.after_round == 14


async def test_a_cache_predating_forks_entirely_reads_as_no_fork(tmp_path: Path) -> None:
    """Caches older than the resume-at-round feature carry neither key."""
    cache = _legacy_cache(replace_agent_source=None, resume_at_round_source=None)
    del cache["resume_at_round_source"]
    run_dir = _write_run(tmp_path=tmp_path, cache=cache)

    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash=None,
    )

    assert summary is not None
    assert summary.total_messages == 999
    assert summary.fork_at_round_source is None
