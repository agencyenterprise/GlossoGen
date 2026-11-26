"""`glossogen transcript` and `glossogen install-skill`, from the arguments to the files written.

Driven through `main` with a patched `sys.argv`, like the other command tests.
"""

from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.models.event import MessageSent, SimulationStarted
from glossogen.models.message import SimulationMessage
from glossogen.run_storage.run_file_paths import event_log_path

SCENARIO = "veyru"


def _write_run(runs_dir: Path) -> Path:
    """A run whose log holds its start and one link message in round 1."""
    run_dir = runs_dir / SCENARIO / "1700000000"
    run_dir.mkdir(parents=True)
    events = [
        SimulationStarted(
            round_number=0,
            run_id=f"{SCENARIO}/1700000000",
            scenario_name=SCENARIO,
            scenario_description="A scenario",
            channel_ids=["link"],
            provider="anthropic",
        ),
        MessageSent(
            round_number=1,
            message=SimulationMessage(
                message_id="m-1",
                channel_id="link",
                sender_agent_id="field_observer",
                sender_display_name="Field Observer",
                text="T bright",
                timestamp=datetime(2026, 8, 1, tzinfo=UTC),
                round_number=1,
            ),
            token_count=3,
        ),
    ]
    log_path = event_log_path(run_dir=run_dir, scenario_name=SCENARIO)
    log_path.write_text("\n".join(event.model_dump_json() for event in events) + "\n")
    return run_dir


def _run_cli(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["glossogen", *argv])
    main()


def test_transcript_prints_the_readme_path_and_each_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _write_run(runs_dir=tmp_path / "runs")

    _run_cli(argv=["transcript", SCENARIO, "--run-dir", str(run_dir)], monkeypatch=monkeypatch)

    printed = capsys.readouterr().out
    assert printed.startswith("Scenario README: ")
    assert printed.splitlines()[0].endswith("README.md")
    assert "=== Before round 1 ===\nRun: veyru/1700000000" in printed
    assert "=== Round 1 ===\n[field_observer -> #link] T bright" in printed


def test_transcript_writes_one_file_per_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(runs_dir=tmp_path / "runs")
    out_dir = tmp_path / "transcript"

    _run_cli(
        argv=["transcript", SCENARIO, "--run-dir", str(run_dir), "--out-dir", str(out_dir)],
        monkeypatch=monkeypatch,
    )

    assert sorted(path.name for path in out_dir.iterdir()) == ["round_00.txt", "round_01.txt"]
    assert (out_dir / "round_00.txt").read_text().startswith("Scenario README: ")
    assert "[field_observer -> #link] T bright" in (out_dir / "round_01.txt").read_text()


def _shipped_skill_md() -> bytes:
    return (
        resources.files("glossogen.agent_skills").joinpath("analyze-runs", "SKILL.md").read_bytes()
    )


def test_install_skill_copies_every_file_of_the_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "skills"

    _run_cli(argv=["install-skill", "--target-dir", str(target)], monkeypatch=monkeypatch)

    assert (target / "analyze-runs" / "SKILL.md").read_bytes() == _shipped_skill_md()
    assert (target / "analyze-runs" / "references" / "behaviour-list.md").is_file()


def test_install_skill_refuses_an_existing_folder_without_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "skills"
    (target / "analyze-runs").mkdir(parents=True)
    (target / "analyze-runs" / "SKILL.md").write_text("an older copy")

    with pytest.raises(SystemExit, match="--replace"):
        _run_cli(argv=["install-skill", "--target-dir", str(target)], monkeypatch=monkeypatch)

    assert (target / "analyze-runs" / "SKILL.md").read_text() == "an older copy"


def test_install_skill_replaces_a_folder_or_a_link_with_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "skills"
    target.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (target / "analyze-runs").symlink_to(elsewhere)

    _run_cli(
        argv=["install-skill", "--target-dir", str(target), "--replace"], monkeypatch=monkeypatch
    )

    assert not (target / "analyze-runs").is_symlink()
    assert (target / "analyze-runs" / "SKILL.md").read_bytes() == _shipped_skill_md()
    assert elsewhere.is_dir()
