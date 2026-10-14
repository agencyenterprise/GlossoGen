"""The filesystem snapshots and command effects dead_drop's run-detail extension serves."""

from typing import Any

import pytest

from glossogen.models.event import SimulationStarted, ToolCallInvoked, ToolResultReceived
from glossogen.scenarios.dead_drop.filesystem_snapshot import RoundSnapshot, round_snapshots
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER, PROMPTS_DIR, TMP_PATH
from glossogen.scenarios.dead_drop.run_detail_extension import (
    DeadDropFsEffectKind,
    DeadDropRunDetailExtension,
    DeadDropRunExtras,
    effects_by_call_id,
)
from glossogen.template_renderer import TemplateRenderer
from tests.scenarios.dead_drop.dead_drop_wiring import Wired, wire

pytestmark = pytest.mark.xdist_group("dead_drop")

ROUND_ONE_COMMANDS: list[tuple[str, str]] = [
    ("ana", "mkdir -p /tmp/drop/sub && echo hello > /tmp/drop/sub/a.txt"),
    ("ana", "echo more >> /tmp/drop/sub/a.txt"),
    ("ben", "cp -r /tmp/drop ~/copy; mv /tmp/drop/sub/a.txt /tmp/moved.txt"),
    ("ben", "printf 'x\\n' | tee -a /tmp/moved.txt > /dev/null"),
    ("ana", "sed -i 's/hello/HELLO/' /tmp/moved.txt; touch /tmp/empty; rm -r /tmp/drop"),
    ("ana", "cp ~/cases/round_01.txt /tmp/case.txt"),
    ("ana", "echo note > ~/note.txt; mkdir ~/keep; cp -r ~/keep /tmp/kept"),
    ("ben", "cat /tmp/moved.txt; cat /tmp/case.txt"),
]
ROUND_TWO_COMMANDS: list[tuple[str, str]] = [
    ("ana", "rm /tmp/empty; echo r2 > /tmp/r2.txt; mv ~/note.txt /tmp/note.txt"),
]


def snapshots_of(wired: Wired) -> list[RoundSnapshot]:
    knobs = wired.scenario.get_knobs()
    return round_snapshots(
        events=wired.logger.events,
        fs_isolated=knobs.fs_isolated,
        case_in_file=knobs.case_delivery.value == "file",
        renderer=TemplateRenderer(prompts_dirs=[PROMPTS_DIR]),
    )


async def live_files(wired: Wired) -> dict[tuple[str | None, str], tuple[str, list[str]]]:
    """Every file on the live server: (tmp_of, path) to (content, authors)."""
    server = wired.scenario._server  # pyright: ignore[reportPrivateUsage]
    volumes = server._volumes  # pyright: ignore[reportPrivateUsage]
    isolated = wired.scenario.get_knobs().fs_isolated
    found: dict[tuple[str | None, str], tuple[str, list[str]]] = {}
    for path in volumes.server.get_all_paths():
        if await volumes.server.is_file(path=path):
            content = await volumes.server.read_file(path=path)
            found[(None, path)] = (content, server.authors_of(agent_id="ana", path=path))
    for agent_id, tmp in volumes.tmp_by_agent.items():
        tmp_of: str | None = None
        if isolated:
            tmp_of = agent_id
        for inner_path in tmp.get_all_paths():
            if not await tmp.is_file(path=inner_path):
                continue
            path = TMP_PATH + inner_path
            content = await tmp.read_file(path=inner_path)
            found[(tmp_of, path)] = (content, server.authors_of(agent_id=agent_id, path=path))
    return found


def snapshot_files(snapshot: RoundSnapshot) -> dict[tuple[str | None, str], tuple[str, list[str]]]:
    return {(file.tmp_of, file.path): (file.content, file.authors) for file in snapshot.files}


@pytest.mark.parametrize("fs_isolated", [False, True])
@pytest.mark.parametrize("case_delivery", ["file", "briefing"])
async def test_the_replayed_snapshot_is_the_live_filesystem(
    monkeypatch: pytest.MonkeyPatch, fs_isolated: bool, case_delivery: str
) -> None:
    """Each round's snapshot, rebuilt from the log alone, holds the files, contents and
    authors the live server holds at that point."""
    wired = await wire(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides={"fs_isolated": fs_isolated, "case_delivery": case_delivery},
    )
    for agent_id, command in ROUND_ONE_COMMANDS:
        await wired.run(agent_id=agent_id, command=command)
    [round_one] = snapshots_of(wired=wired)
    assert snapshot_files(snapshot=round_one) == await live_files(wired=wired)

    await wired.finish_round(trigger=BOTH_SUBMITTED_TRIGGER, read_briefings=True)
    for agent_id, command in ROUND_TWO_COMMANDS:
        await wired.run(agent_id=agent_id, command=command)
    first, second = snapshots_of(wired=wired)
    assert snapshot_files(snapshot=first) == snapshot_files(snapshot=round_one)
    assert snapshot_files(snapshot=second) == await live_files(wired=wired)


async def test_a_snapshot_records_who_changed_each_file_last_and_who_can_read_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ana", command="echo hi > /tmp/drop.txt; echo mine > ~/own.txt")
    await wired.finish_round(trigger=BOTH_SUBMITTED_TRIGGER, read_briefings=True)
    await wired.run(agent_id="ben", command="echo reply >> /tmp/drop.txt")
    first, second = snapshots_of(wired=wired)
    by_path = {file.path: file for file in second.files}
    drop = by_path["/tmp/drop.txt"]
    assert (drop.content, drop.authors, drop.readers) == (
        "hi\nreply\n",
        ["ana", "ben"],
        ["ana", "ben"],
    )
    assert (drop.last_changed_by, drop.last_changed_round) == ("ben", 2)
    own = by_path["/home/ana/own.txt"]
    assert (own.readers, own.last_changed_round) == (["ana"], 1)
    assert by_path["/home/ana/cases/round_02.txt"].last_changed_by == "root"
    assert "/home/ana/cases/round_02.txt" not in {file.path for file in first.files}
    assert {directory.path for directory in second.directories} >= {"/home", "/home/ana", "/tmp"}


async def logged_call(wired: Wired, agent_id: str, call_id: str, command: str) -> None:
    """``agent_id`` runs ``command`` as one ``run_command`` call, logged as the runner logs it."""
    round_number = wired.runtime.current_round
    arguments: dict[str, Any] = {"command": command}
    wired.logger.events.append(
        ToolCallInvoked(
            round_number=round_number,
            agent_id=agent_id,
            call_id=call_id,
            tool_name="run_command",
            arguments=arguments,
        )
    )
    result = await wired.run(agent_id=agent_id, command=command)
    wired.logger.events.append(
        ToolResultReceived(
            round_number=round_number,
            agent_id=agent_id,
            call_id=call_id,
            tool_name="run_command",
            arguments=arguments,
            result=result,
        )
    )


async def test_each_command_gets_the_changes_and_reads_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeats in a row are counted once; a command outside any logged call gets nothing."""
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await logged_call(
        wired=wired,
        agent_id="ana",
        call_id="call-ana",
        command="echo hi > /tmp/x; for i in 1 2 3; do touch /tmp/x; done; cp /tmp/x ~/y",
    )
    await logged_call(wired=wired, agent_id="ben", call_id="call-ben", command="cat /tmp/x")
    await wired.run(agent_id="ben", command="echo unlogged > /tmp/z")

    effects = effects_by_call_id(events=wired.logger.events)

    assert set(effects) == {"call-ana", "call-ben"}
    assert [(e.kind, e.path, e.destination, e.count, e.shared) for e in effects["call-ana"]] == [
        (DeadDropFsEffectKind.WRITE, "/tmp/x", None, 1, True),
        (DeadDropFsEffectKind.TOUCH, "/tmp/x", None, 3, True),
        (DeadDropFsEffectKind.COPY, "/tmp/x", "/home/ana/y", 1, False),
    ]
    [read] = effects["call-ben"]
    assert (read.kind, read.path, read.authors) == (DeadDropFsEffectKind.READ, "/tmp/x", ["ana"])


def started(knobs: dict[str, Any]) -> SimulationStarted:
    return SimulationStarted(
        round_number=0,
        run_id="dead_drop/1",
        scenario_name="dead_drop",
        scenario_description="",
        channel_ids=[],
        scenario_config=knobs,
        provider="self-hosted",
    )


async def test_the_extension_serves_each_round_and_reads_the_run_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A config recorded before ``case_delivery`` existed lays out case files, as those runs did."""
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ana", command="echo hi > /tmp/drop.txt")
    knobs = wired.scenario.get_knobs().model_dump(mode="json")
    extension = DeadDropRunDetailExtension()

    extras = extension.build_extras(
        events=[started(knobs=knobs), *wired.logger.events], agents_by_id={}, messages=[]
    )
    assert isinstance(extras, DeadDropRunExtras)
    [round_one] = extras.rounds
    paths = {file.path for file in round_one.files}
    assert {"/tmp/drop.txt", "/home/ana/cases/round_01.txt", "/etc/passwd"} <= paths

    briefing = extension.build_extras(
        events=[started(knobs={**knobs, "case_delivery": "briefing"}), *wired.logger.events],
        agents_by_id={},
        messages=[],
    )
    assert "/home/ana/cases/round_01.txt" not in {file.path for file in briefing.rounds[0].files}

    legacy_knobs = {key: value for key, value in knobs.items() if key != "case_delivery"}
    legacy = extension.build_extras(
        events=[started(knobs=legacy_knobs), *wired.logger.events], agents_by_id={}, messages=[]
    )
    assert "/home/ana/cases/round_01.txt" in {file.path for file in legacy.rounds[0].files}
