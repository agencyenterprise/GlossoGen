"""`rewrite_run_jsonl`: what a derived run's copied log says about the run and its code."""

import json
from pathlib import Path

from glossogen.models.glossogen_build import GlossogenBuild
from glossogen.run_derivation.run_jsonl_rewriter import drop_simulation_ended, rewrite_run_jsonl


def _write_source_log(path: Path) -> None:
    lines = [
        {
            "event_type": "simulation_started",
            "run_id": "veyru/1",
            "glossogen_build": {
                "version": "0.1.0",
                "git_commit": "old",
                "has_uncommitted_changes": False,
            },
        },
        {"event_type": "message_sent", "message": {"message_id": "m-1", "text": "hello"}},
        {"event_type": "simulation_ended"},
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_the_copied_start_names_the_new_run_and_the_deriving_build(tmp_path: Path) -> None:
    log_path = tmp_path / "veyru.jsonl"
    _write_source_log(path=log_path)
    deriving_build = GlossogenBuild(version="0.2.0", git_commit="new", has_uncommitted_changes=True)

    rewrite_run_jsonl(
        log_path=log_path,
        new_run_id="veyru/2",
        glossogen_build=deriving_build,
        message_edits={"m-1": "edited"},
        should_drop_event=drop_simulation_ended,
    )

    events = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert [event["event_type"] for event in events] == ["simulation_started", "message_sent"]
    assert events[0]["run_id"] == "veyru/2"
    assert events[0]["glossogen_build"] == deriving_build.model_dump(mode="json")
    assert events[1]["message"]["text"] == "edited"
