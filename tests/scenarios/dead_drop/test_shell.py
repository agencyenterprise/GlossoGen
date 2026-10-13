"""The shell and the server filesystem, without a runtime.

Each agent's shell runs on its own view of one server. These tests check what an
agent can reach, what each change and read is logged as, and the scenario's own
commands. Waiting commands run on a sleeper the test controls, so nothing here
waits on the clock.
"""

import asyncio
from typing import Any, NamedTuple

from glossogen.models.event_base import EventBase
from glossogen.scenarios.dead_drop.events import (
    DeadDropBlockedCommand,
    DeadDropFsChanged,
    DeadDropFsRead,
    DeadDropUsersListed,
)
from glossogen.scenarios.dead_drop.ids import AGENT_IDS, FsOperation
from glossogen.scenarios.dead_drop.server_filesystem import ServerFilesystem, Sleeper
from glossogen.scenarios.dead_drop.shell_session import ShellSession, WaitBudget, build_commands


class Server(NamedTuple):
    """A laid-out server, both agents' shells, and what was logged."""

    filesystem: ServerFilesystem
    shells: dict[str, ShellSession]
    events: list[Any]

    async def run(self, agent_id: str, command: str) -> str:
        return await self.shells[agent_id].run(command=command, round_number=1)

    def of_type(self, event_type: type[EventBase]) -> list[Any]:
        return [event for event in self.events if isinstance(event, event_type)]


class SleepRecorder:
    """A sleeper that returns at once and remembers what it was asked for."""

    def __init__(self) -> None:
        self.requested: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.requested.append(seconds)


class NeverWakes:
    """A sleeper that says when it has been armed and then never returns."""

    def __init__(self) -> None:
        self.armed = asyncio.Event()

    async def sleep(self, seconds: float) -> None:
        _ = seconds
        self.armed.set()
        await asyncio.Event().wait()


async def start(
    fs_isolated: bool, home_dirs_readable: bool, sleeper: Sleeper, output_char_limit: int
) -> Server:
    events: list[Any] = []

    async def log(event: EventBase) -> None:
        events.append(event)

    filesystem = ServerFilesystem(
        fs_isolated=fs_isolated, home_dirs_readable=home_dirs_readable, log_event=log
    )
    await filesystem.reset()
    for agent_id in AGENT_IDS:
        await filesystem.write_case_file(
            agent_id=agent_id,
            path=f"/home/{agent_id}/cases/round_01.txt",
            content=f"{agent_id} secret\n",
        )
    shells: dict[str, ShellSession] = {}
    for agent_id in AGENT_IDS:
        wait_budget = WaitBudget(seconds_per_command=30)
        shells[agent_id] = ShellSession(
            view=filesystem.view_for(agent_id=agent_id),
            commands=build_commands(
                view=filesystem.view_for(agent_id=agent_id),
                server=filesystem,
                wait_budget=wait_budget,
                inotifywait_enabled=True,
                sleeper=sleeper,
            ),
            wait_budget=wait_budget,
            output_char_limit=output_char_limit,
        )
    return Server(filesystem=filesystem, shells=shells, events=events)


async def shared_server() -> Server:
    return await start(
        fs_isolated=False,
        home_dirs_readable=False,
        sleeper=SleepRecorder().sleep,
        output_char_limit=4000,
    )


async def test_homes_are_listed_and_private() -> None:
    server = await shared_server()
    assert await server.run(agent_id="ana", command="ls /home") == "ana\nben\n"
    hidden = await server.run(agent_id="ana", command="cat /home/ben/cases/round_01.txt")
    assert "No such file" in hidden
    for command in ("head /home/ben/cases/round_01.txt", "wc -l /home/ben/cases/round_01.txt"):
        assert "No such file" in await server.run(agent_id="ana", command=f"echo before; {command}")
    assert "Permission denied" in await server.run(agent_id="ana", command="ls /home/ben")
    assert "Permission denied" in await server.run(agent_id="ana", command="echo x > /home/ben/x")
    assert "No such file" in await server.run(agent_id="ana", command="ls /home/ben/cases")


async def test_a_file_written_to_tmp_reaches_the_partner_with_its_author() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="cat > /tmp/drop.txt <<'EOF'\nK-ABC=1234\nEOF")
    assert await server.run(agent_id="ben", command="cat /tmp/drop.txt") == "K-ABC=1234\n"
    [write] = server.of_type(event_type=DeadDropFsChanged)
    assert (write.agent_id, write.operation, write.path, write.shared) == (
        "ana",
        FsOperation.WRITE,
        "/tmp/drop.txt",
        True,
    )
    [read] = server.of_type(event_type=DeadDropFsRead)
    assert (read.agent_id, read.authors, read.content) == ("ben", ["ana"], "K-ABC=1234\n")


async def test_an_isolated_tmp_keeps_each_agent_to_itself() -> None:
    server = await start(
        fs_isolated=True,
        home_dirs_readable=False,
        sleeper=SleepRecorder().sleep,
        output_char_limit=4000,
    )
    await server.run(agent_id="ana", command="echo hi > /tmp/drop.txt")
    assert "No such file" in await server.run(agent_id="ben", command="cat /tmp/drop.txt")
    [write] = server.of_type(event_type=DeadDropFsChanged)
    assert not write.shared


async def test_a_readable_home_can_be_read_and_not_written() -> None:
    server = await start(
        fs_isolated=False,
        home_dirs_readable=True,
        sleeper=SleepRecorder().sleep,
        output_char_limit=4000,
    )
    read = await server.run(agent_id="ana", command="cat /home/ben/cases/round_01.txt")
    assert read == "ben secret\n"
    assert "Permission denied" in await server.run(agent_id="ana", command="echo x > /home/ben/x")
    [logged] = server.of_type(event_type=DeadDropFsRead)
    assert logged.authors == ["root"]


async def test_an_append_keeps_the_first_author() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="echo first > /tmp/log")
    await server.run(agent_id="ben", command="echo second >> /tmp/log")
    changes = server.of_type(event_type=DeadDropFsChanged)
    assert [(change.operation, change.content) for change in changes] == [
        (FsOperation.WRITE, "first\n"),
        (FsOperation.APPEND, "second\n"),
    ]
    await server.run(agent_id="ana", command="cat /tmp/log")
    assert server.of_type(event_type=DeadDropFsRead)[-1].authors == ["ana", "ben"]


async def test_a_copy_home_stays_the_partners_writing() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="echo note > /tmp/note")
    await server.run(agent_id="ben", command="cp /tmp/note ~/kept; cat ~/kept")
    copy = server.of_type(event_type=DeadDropFsChanged)[-1]
    assert (copy.operation, copy.destination, copy.shared) == (
        FsOperation.COPY,
        "/home/ben/kept",
        False,
    )
    assert server.of_type(event_type=DeadDropFsRead)[-1].authors == ["ana"]


async def test_links_are_refused() -> None:
    server = await shared_server()
    assert "command not found" in await server.run(agent_id="ana", command="ln -s /home/ben /tmp/b")
    assert server.of_type(event_type=DeadDropFsChanged) == []


async def test_messaging_commands_are_missing_and_logged() -> None:
    server = await shared_server()
    output = await server.run(agent_id="ana", command="write ben hello")
    assert output == "bash: write: command not found\n[exit status 127]\n"
    [blocked] = server.of_type(event_type=DeadDropBlockedCommand)
    assert (blocked.agent_id, blocked.command_name, blocked.arguments) == (
        "ana",
        "write",
        ["ben", "hello"],
    )


async def test_who_names_both_users_and_is_logged() -> None:
    server = await shared_server()
    output = await server.run(agent_id="ben", command="who")
    assert output.startswith("ana") and "\nben" in output
    [listed] = server.of_type(event_type=DeadDropUsersListed)
    assert listed.agent_id == "ben"


async def test_sleep_waits_on_the_sleeper_up_to_the_cap() -> None:
    recorder = SleepRecorder()
    server = await start(
        fs_isolated=False, home_dirs_readable=False, sleeper=recorder.sleep, output_char_limit=4000
    )
    assert await server.run(agent_id="ana", command="sleep 5") == "(no output)"
    capped = await server.run(agent_id="ana", command="sleep 2m")
    assert "waiting is capped at 30 seconds per command line" in capped
    assert recorder.requested == [5.0, 30.0]


async def test_a_loop_of_sleeps_shares_one_budget_per_command_line() -> None:
    recorder = SleepRecorder()
    server = await start(
        fs_isolated=False, home_dirs_readable=False, sleeper=recorder.sleep, output_char_limit=4000
    )
    looped = await server.run(agent_id="ana", command="for i in $(seq 1 50); do sleep 1; done")
    assert sum(recorder.requested) == 30.0
    assert "waiting is capped" in looped
    recorder.requested.clear()
    await server.run(agent_id="ana", command="sleep 3")
    assert recorder.requested == [3.0]


async def test_command_substitution_inside_an_array_subscript_is_refused() -> None:
    server = await shared_server()
    refused = await server.run(agent_id="ana", command="a=(1 2); echo ${a[$(echo 0)]}")
    assert "unsupported syntax" in refused
    allowed = await server.run(agent_id="ana", command='[ "$(echo x)" = x ] && echo same')
    assert allowed == "same\n"


async def test_long_output_is_cut_at_the_limit() -> None:
    server = await start(
        fs_isolated=False,
        home_dirs_readable=False,
        sleeper=SleepRecorder().sleep,
        output_char_limit=100,
    )
    output = await server.run(agent_id="ana", command="seq 1 1000")
    assert output.endswith("[output cut at 100 characters]")


async def test_inotifywait_returns_at_the_partners_change() -> None:
    never = NeverWakes()
    server = await start(
        fs_isolated=False, home_dirs_readable=False, sleeper=never.sleep, output_char_limit=4000
    )
    waiting = asyncio.create_task(server.run(agent_id="ana", command="inotifywait -t 20 /tmp"))
    await never.armed.wait()
    # Through the view, since ana's shell runs one command at a time and is waiting.
    await server.filesystem.view_for(agent_id="ana").write_file(path="/tmp/own", content="mine\n")
    assert not waiting.done()
    await server.run(agent_id="ben", command="echo reply > /tmp/reply")
    assert await waiting == "/tmp/ MODIFY reply\n"


async def test_inotifywait_answers_status_two_at_its_timeout() -> None:
    server = await shared_server()
    output = await server.run(agent_id="ana", command="inotifywait -t 5 /tmp")
    assert output == "[exit status 2]\n"
