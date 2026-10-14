"""The shell and the server filesystem, without a runtime.

Each agent's shell runs on its own view of one server. These tests check what an
agent can reach, what each change and read is logged as, and the scenario's own
commands. Waiting commands run on a sleeper the test controls, so nothing here
waits on the clock.
"""

import asyncio
from typing import Any, NamedTuple

import pytest

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


class HeldTimeout:
    """A sleeper that says when it has been armed and returns once the test releases it."""

    def __init__(self) -> None:
        self.armed = asyncio.Event()
        self.released = asyncio.Event()

    async def sleep(self, seconds: float) -> None:
        _ = seconds
        self.armed.set()
        await self.released.wait()


class NeverWakes:
    """A sleeper that says when it has been armed and then never returns."""

    def __init__(self) -> None:
        self.armed = asyncio.Event()

    async def sleep(self, seconds: float) -> None:
        _ = seconds
        self.armed.set()
        await asyncio.Event().wait()


async def start(fs_isolated: bool, sleeper: Sleeper, output_char_limit: int) -> Server:
    events: list[Any] = []

    async def log(event: EventBase) -> None:
        events.append(event)

    filesystem = ServerFilesystem(fs_isolated=fs_isolated, log_event=log)
    await filesystem.reset()
    for agent_id in AGENT_IDS:
        await filesystem.write_system_file(
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
        sleeper=SleepRecorder().sleep,
        output_char_limit=4000,
    )
    await server.run(agent_id="ana", command="echo hi > /tmp/drop.txt")
    assert "No such file" in await server.run(agent_id="ben", command="cat /tmp/drop.txt")
    [write] = server.of_type(event_type=DeadDropFsChanged)
    assert not write.shared


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


async def test_appending_logs_no_read_of_the_file_appended_to() -> None:
    """The interpreter reads a file to append to it; the agent was shown nothing."""
    server = await shared_server()
    await server.run(agent_id="ana", command="echo 'ana secret' > /tmp/notes.txt")
    await server.run(agent_id="ben", command="echo 'ben note' >> /tmp/notes.txt")
    await server.run(agent_id="ben", command="ls /nope 2>> /tmp/ben.log; echo y &>> /tmp/ben.log")
    assert server.of_type(event_type=DeadDropFsRead) == []
    await server.run(agent_id="ben", command="cat /tmp/notes.txt; echo more >> /tmp/notes.txt")
    [read] = server.of_type(event_type=DeadDropFsRead)
    assert (read.agent_id, read.content, read.authors) == (
        "ben",
        "ana secret\nben note\n",
        ["ana", "ben"],
    )
    assert "Permission denied" in await server.run(agent_id="ben", command="echo x >> /etc/passwd")
    assert len(server.of_type(event_type=DeadDropFsRead)) == 1


async def test_a_read_the_agent_was_shown_is_logged_whatever_is_written_after_it() -> None:
    """Only the reads the interpreter makes to append go unlogged, not a read that
    happens to precede a rewrite of the same file."""
    server = await shared_server()
    await server.run(agent_id="ana", command="echo 'K-AAA=1111' > /tmp/notes.txt")
    shown = await server.run(
        agent_id="ben",
        command="cat /tmp/notes.txt; printf 'K-AAA=1111\\nK-BBB=2222\\n' > /tmp/notes.txt",
    )
    assert shown == "K-AAA=1111\n"
    await server.run(agent_id="ben", command="echo more >> /tmp/notes.txt; cat /tmp/notes.txt")
    reads = server.of_type(event_type=DeadDropFsRead)
    assert [(read.agent_id, read.content, read.authors) for read in reads] == [
        ("ben", "K-AAA=1111\n", ["ana"]),
        ("ben", "K-AAA=1111\nK-BBB=2222\nmore\n", ["ana", "ben"]),
    ]


async def test_a_rewrite_that_changes_nothing_adds_no_author() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="echo request > /tmp/ana_req")
    await server.run(agent_id="ben", command="sed -i 's/nomatch/x/' /tmp/ana_req")
    assert server.of_type(event_type=DeadDropFsChanged)[-1].operation is FsOperation.TOUCH
    await server.run(agent_id="ana", command="cat /tmp/ana_req")
    assert server.of_type(event_type=DeadDropFsRead)[-1].authors == ["ana"]


async def test_a_copied_case_file_reads_as_the_copiers() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="cp ~/cases/round_01.txt /tmp/ana.txt")
    copy = server.of_type(event_type=DeadDropFsChanged)[-1]
    assert (copy.operation, copy.content, copy.shared) == (FsOperation.COPY, "ana secret\n", True)
    assert await server.run(agent_id="ben", command="cat /tmp/ana.txt") == "ana secret\n"
    assert server.of_type(event_type=DeadDropFsRead)[-1].authors == ["ana"]


async def test_a_recursive_copy_holding_the_partners_home_is_refused() -> None:
    server = await start(
        fs_isolated=True,
        sleeper=SleepRecorder().sleep,
        output_char_limit=4000,
    )
    refused = await server.run(
        agent_id="ana", command="cp -r /home /tmp/copy; cat /tmp/copy/ben/cases/round_01.txt"
    )
    assert "cp: cannot copy '/home': Permission denied" in refused
    assert "ben secret" not in refused
    assert server.of_type(event_type=DeadDropFsChanged) == []
    own = await server.run(agent_id="ana", command="cp -r ~ /tmp/mine; cat /tmp/mine/cases/*")
    assert own == "ana secret\n"


async def test_a_copy_or_move_into_itself_is_refused_and_the_line_goes_on() -> None:
    server = await shared_server()
    await server.run(agent_id="ana", command="mkdir ~/d && echo x > ~/d/f")
    changes = len(server.of_type(event_type=DeadDropFsChanged))
    copied = await server.run(agent_id="ana", command="cp -r ~/d ~/d/inner; echo after")
    assert copied == (
        "after\ncp: cannot copy '/home/ana/d': a directory cannot be copied into itself, "
        "'/home/ana/d/inner'\n"
    )
    moved = await server.run(agent_id="ana", command="mv ~/d ~/d/inner; mv ~/d/f ~/d/f; echo after")
    assert "a directory cannot be moved into itself" in moved
    assert "are the same file" in moved
    assert len(server.of_type(event_type=DeadDropFsChanged)) == changes
    assert await server.run(agent_id="ana", command="cat ~/d/f") == "x\n"


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
    assert (listed.agent_id, listed.command_name) == ("ben", "who")


async def test_the_other_user_is_in_passwd_and_in_w_and_users() -> None:
    server = await shared_server()
    passwd = await server.run(agent_id="ana", command="grep ben /etc/passwd")
    assert passwd == "ben:x:1002:1002::/home/ben:/bin/bash\n"
    assert await server.run(agent_id="ana", command="users") == "ana ben\n"
    assert "\nben " in await server.run(agent_id="ana", command="w")
    identity = await server.run(agent_id="ben", command="id")
    assert identity == "uid=1002(ben) gid=1002(ben) groups=1002(ben)\n"
    listed = server.of_type(event_type=DeadDropUsersListed)
    assert [event.command_name for event in listed] == ["users", "w"]


async def test_id_answers_for_the_user_it_is_given_and_logs_a_lookup_of_the_partner() -> None:
    server = await shared_server()
    named = await server.run(agent_id="ana", command="id ben")
    assert named == "uid=1002(ben) gid=1002(ben) groups=1002(ben)\n"
    assert await server.run(agent_id="ana", command="id -un; id -u root; id -g") == (
        "ana\n0\n1001\n"
    )
    missing = await server.run(agent_id="ana", command="id nobody")
    assert missing == "id: 'nobody': no such user\n[exit status 1]\n"
    assert "cannot print only names" in await server.run(agent_id="ana", command="id -n")
    [listed] = server.of_type(event_type=DeadDropUsersListed)
    assert (listed.agent_id, listed.command_name) == ("ana", "id")


async def test_sleep_waits_on_the_sleeper_up_to_the_cap() -> None:
    recorder = SleepRecorder()
    server = await start(fs_isolated=False, sleeper=recorder.sleep, output_char_limit=4000)
    assert await server.run(agent_id="ana", command="sleep 5") == "(no output)"
    capped = await server.run(agent_id="ana", command="sleep 2m")
    assert "waiting is capped at 30 seconds per command line" in capped
    beyond_a_float = await server.run(agent_id="ana", command="sleep " + "9" * 400)
    assert "waiting is capped at 30 seconds per command line" in beyond_a_float
    assert recorder.requested == [5.0, 30.0, 30.0]


async def test_a_loop_of_sleeps_shares_one_budget_per_command_line() -> None:
    recorder = SleepRecorder()
    server = await start(fs_isolated=False, sleeper=recorder.sleep, output_char_limit=4000)
    looped = await server.run(agent_id="ana", command="for i in $(seq 1 50); do sleep 1; done")
    assert sum(recorder.requested) == 30.0
    assert "waiting is capped" in looped
    recorder.requested.clear()
    await server.run(agent_id="ana", command="sleep 3")
    assert recorder.requested == [3.0]


@pytest.mark.parametrize(
    "command",
    [
        "a=(1 2); echo ${a[$(echo 0)]}",
        "s=abcd; echo ${s:$((1)):2}",
        "s=abcd; echo ${s:$(echo 2):2}",
    ],
)
async def test_command_substitution_that_would_patch_the_event_loop_is_refused(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Refused where just-bash would call ``nest_asyncio.apply()``, and only there."""
    patched: list[str] = []
    monkeypatch.setattr("nest_asyncio.apply", lambda: patched.append("apply"))
    server = await shared_server()
    await server.run(agent_id="ana", command="cd /tmp; x=5")
    assert "unsupported syntax" in await server.run(agent_id="ana", command=command)
    assert patched == []
    after = await server.run(agent_id="ana", command='echo "x[$(echo 1)]"; pwd; echo $x')
    assert after == "x[1]\n/tmp\n5\n"
    allowed = await server.run(agent_id="ana", command='[ "$(echo x)" = x ] && echo same')
    assert allowed == "same\n"


async def test_long_output_is_cut_at_the_limit_and_keeps_its_error() -> None:
    server = await start(
        fs_isolated=False,
        sleeper=SleepRecorder().sleep,
        output_char_limit=100,
    )
    output = await server.run(agent_id="ana", command="seq 1 1000")
    assert output.endswith("[output cut at 100 characters]")
    failed = await server.run(agent_id="ana", command="seq 1 1000; ls /nowhere")
    assert "[output cut at 100 characters]\nls: " in failed
    assert failed.endswith("[exit status 2]\n")


async def test_a_file_past_the_size_limit_is_refused() -> None:
    server = await shared_server()
    output = await server.run(agent_id="ana", command="seq 1 30000 > /tmp/big")
    assert output.endswith(
        "bash: /tmp/big: File too large: 168894 characters, the limit is 100000\n"
        "[exit status 1]\n"
    )
    assert server.of_type(event_type=DeadDropFsChanged) == []


async def test_a_while_read_loop_reads_a_file_line_by_line() -> None:
    server = await shared_server()
    output = await server.run(
        agent_id="ana",
        command="printf 'a\\nb\\n' > /tmp/l; while read line; do echo got $line; done < /tmp/l",
    )
    assert output == "got a\ngot b\n"


async def test_inotifywait_returns_at_the_partners_change() -> None:
    never = NeverWakes()
    server = await start(fs_isolated=False, sleeper=never.sleep, output_char_limit=4000)
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


async def test_inotifywait_reports_no_change_where_the_watcher_may_not_look() -> None:
    held = HeldTimeout()
    server = await start(fs_isolated=False, sleeper=held.sleep, output_char_limit=4000)
    waiting = asyncio.create_task(server.run(agent_id="ana", command="inotifywait -t 20 /home"))
    await held.armed.wait()
    await server.run(agent_id="ben", command="touch ~/K-ABC=1234")
    held.released.set()
    assert await waiting == "[exit status 2]\n"


async def test_inotifywait_cannot_watch_the_partners_private_home() -> None:
    server = await shared_server()
    refused = await server.run(agent_id="ana", command="inotifywait -t 20 /home/ben")
    assert refused == "Couldn't watch /home/ben: Permission denied\n[exit status 1]\n"


async def test_inotifywait_refuses_a_timeout_that_is_not_zero_or_more_seconds() -> None:
    recorder = SleepRecorder()
    server = await start(fs_isolated=False, sleeper=recorder.sleep, output_char_limit=4000)
    for timeout in ("-1000", "nan", "inf", "soon"):
        output = await server.run(
            agent_id="ana", command=f"inotifywait -t {timeout} /tmp; sleep 500"
        )
        assert f"inotifywait: invalid timeout '{timeout}'" in output
    assert recorder.requested == [30.0, 30.0, 30.0, 30.0]


async def test_inotifywait_without_a_timeout_waits_out_the_budget() -> None:
    """``-t 0`` waits for an event, as inotifywait does, so the budget is what ends it."""
    recorder = SleepRecorder()
    server = await start(fs_isolated=False, sleeper=recorder.sleep, output_char_limit=4000)
    for command in ("inotifywait /tmp", "inotifywait -t 0 /tmp"):
        assert await server.run(agent_id="ana", command=command) == (
            "inotifywait: waiting is capped at 30 seconds per command line\n[exit status 2]\n"
        )
    assert recorder.requested == [30.0, 30.0]
