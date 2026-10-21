"""The shared server container: accounts, permissions, commands, snapshots, kills.

Needs a Docker daemon. One container serves the module, restored to empty between
tests.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.ids import AGENT_IDS, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_server.events import SignalGameServerChanged
from glossogen.scenarios.signal_game_server.player_shell import ServerState, format_output
from glossogen.scenarios.signal_game_server.server_activity import ServerActivity
from glossogen.scenarios.signal_game_server.server_changes import ServerChangeKind
from glossogen.scenarios.signal_game_server.server_container import (
    ContainerRole,
    ServerContainer,
    container_name,
)
from glossogen.scenarios.signal_game_server.server_snapshot import NodeKind, empty_snapshot

pytestmark = pytest.mark.xdist_group("signal_game_server_container")

OUTPUT = 4000
TIMEOUT = 20.0


@pytest.fixture(scope="module")
async def container() -> AsyncIterator[ServerContainer]:
    server = ServerContainer(
        users=AGENT_IDS, name=container_name(suffix="test"), role=ContainerRole.PLAYERS
    )
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture
async def clean(container: ServerContainer) -> ServerContainer:
    await container.restore(snapshot=empty_snapshot(users=AGENT_IDS, at=datetime.now(tz=UTC)))
    return container


async def run(container: ServerContainer, user: str, command: str) -> str:
    output = await container.exec_as(
        user=user, command=command, timeout_s=TIMEOUT, output_bytes=OUTPUT
    )
    return format_output(output=output, char_limit=OUTPUT)


async def test_the_accounts_exist_and_a_file_one_writes_the_other_reads(
    clean: ServerContainer,
) -> None:
    assert await run(clean, PLAYER_A, "whoami; id -u; pwd") == "player_a\n1001\n/home/player_a\n"
    assert await run(clean, PLAYER_A, "echo hi > /tmp/x") == "(no output)"
    assert await run(clean, PLAYER_B, "cat /tmp/x") == "hi\n"
    listing = await run(clean, PLAYER_B, "ls -l /tmp/x")
    assert listing.startswith("-rw-r--r-- 1 player_a player_a 3 ")


async def test_chmod_closes_a_file_and_the_sticky_tmp_holds(clean: ServerContainer) -> None:
    await run(clean, PLAYER_A, "echo hi > note; chmod 600 note; touch /tmp/f")
    denied = await run(clean, PLAYER_B, "cat /home/player_a/note")
    assert "Permission denied" in denied
    assert "[exit status 1]" in denied
    assert "Operation not permitted" in await run(clean, PLAYER_B, "rm /tmp/f")
    assert "Operation not permitted" in await run(clean, PLAYER_B, "chmod 777 /tmp/f")


async def test_a_snapshot_diff_attributes_changes_to_their_owners(
    clean: ServerContainer,
) -> None:
    logged: list[SignalGameServerChanged] = []

    async def log(event: EventBase) -> None:
        assert isinstance(event, SignalGameServerChanged)
        logged.append(event)

    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=log),
        round_open=_always_open,
    )
    await run(clean, PLAYER_A, "mkdir d; printf 1011 > d/f; chmod 600 d/f")
    await run(clean, PLAYER_B, "touch /tmp/z")
    assert await state.record(round_number=1) is None
    assert [(event.agent_id, event.change.kind, event.change.path) for event in logged] == [
        (PLAYER_B, ServerChangeKind.WRITE, "/tmp/z"),
        (PLAYER_A, ServerChangeKind.MKDIR, "/home/player_a/d"),
        (PLAYER_A, ServerChangeKind.WRITE, "/home/player_a/d/f"),
    ]
    assert logged[2].change.content == "1011"
    assert logged[2].change.mode == 0o600
    assert state.snapshot.nodes["/home/player_a/d/f"].kind is NodeKind.FILE


async def test_a_command_past_the_quota_is_undone(clean: ServerContainer) -> None:
    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=_drop),
        round_open=_always_open,
    )
    await run(clean, PLAYER_A, "cd /tmp && touch $(seq 1 60)")
    await state.record(round_number=1)
    assert "undone" in state.take_notice(user=PLAYER_A)
    assert await run(clean, PLAYER_A, "ls /tmp | wc -l") == "0\n"


async def test_restore_puts_back_a_snapshot(clean: ServerContainer) -> None:
    await run(clean, PLAYER_A, "printf 1011 > /tmp/x; chmod 600 /tmp/x; mkdir -p a/b")
    kept = await clean.snapshot()
    await run(clean, PLAYER_A, "rm -r /tmp/x a; touch gone")
    await clean.restore(snapshot=kept)
    assert await run(clean, PLAYER_A, "cat /tmp/x; stat -c %a /tmp/x; ls; ls a") == (
        "1011600\na\nb\n"
    )


async def test_a_long_command_is_killed_at_the_timeout(clean: ServerContainer) -> None:
    output = await clean.exec_as(
        user=PLAYER_A, command="echo before; sleep 600", timeout_s=1, output_bytes=OUTPUT
    )
    assert output.timed_out
    assert output.stdout == "before\n"


async def test_killing_a_users_processes_ends_its_command(clean: ServerContainer) -> None:
    waiting = asyncio.ensure_future(
        clean.exec_as(user=PLAYER_B, command="sleep 600", timeout_s=TIMEOUT, output_bytes=OUTPUT)
    )
    await _until_running(clean, user=PLAYER_B, program="sleep")
    await clean.kill_user_processes(user=PLAYER_B)
    output = await waiting
    assert output.timed_out


async def test_a_player_sees_none_of_the_partners_processes(clean: ServerContainer) -> None:
    waiting = asyncio.ensure_future(
        clean.exec_as(user=PLAYER_A, command="sleep 600", timeout_s=TIMEOUT, output_bytes=OUTPUT)
    )
    await _until_running(clean, user=PLAYER_A, program="sleep")
    seen = await run(clean, PLAYER_B, "ps -eo user= | sort -u; ls /proc | grep -c '^[0-9]'")
    assert "player_a" not in seen
    await clean.kill_user_processes(user=PLAYER_A)
    await waiting


async def test_inotifywait_returns_on_the_partners_change(clean: ServerContainer) -> None:
    waiting = asyncio.ensure_future(run(clean, PLAYER_B, "inotifywait -q -t 15 /tmp"))
    await _until_running(clean, user=PLAYER_B, program="inotifywait")
    await run(clean, PLAYER_A, "echo x > /tmp/y")
    assert await waiting == "/tmp/ CREATE y\n"


async def _until_running(container: ServerContainer, user: str, program: str) -> None:
    """Wait until ``user`` has a ``program`` process, seen as root since players see only
    their own."""
    while True:
        found = await container.exec_as_root(
            command=f"pgrep -u {user} {program} | wc -l", timeout_s=TIMEOUT, output_bytes=OUTPUT
        )
        if found.stdout.strip() != "0":
            return
        await asyncio.sleep(0.1)


def _always_open(round_number: int) -> bool:
    _ = round_number
    return True


def _never_open(round_number: int) -> bool:
    _ = round_number
    return False


async def _drop(event: EventBase) -> None:
    _ = event


async def test_the_other_writable_directories_are_closed(clean: ServerContainer) -> None:
    for directory in ("/var/tmp", "/run/lock", "/dev/shm"):
        output = await run(clean, PLAYER_A, f"touch {directory}/x")
        assert "Permission denied" in output, directory


async def test_nothing_a_line_started_outlives_it(clean: ServerContainer) -> None:
    await run(clean, PLAYER_A, "(nohup sleep 300 >/dev/null 2>&1 &); exit 0")
    left = await clean.exec_as_root(
        command="pgrep -u player_a sleep | wc -l", timeout_s=TIMEOUT, output_bytes=OUTPUT
    )
    assert left.stdout.strip() == "0"


async def test_a_fifo_is_undone_as_a_quota_breach(clean: ServerContainer) -> None:
    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=_drop),
        round_open=_always_open,
    )
    await run(clean, PLAYER_A, "mkfifo /tmp/p; touch /tmp/kept")
    await state.record(round_number=1)
    assert "FIFO" in state.take_notice(user=PLAYER_A)
    assert state.take_notice(user=PLAYER_B) == ""
    assert await run(clean, PLAYER_A, "ls /tmp") == "(no output)"


async def test_a_partners_breach_leaves_a_binary_file_byte_for_byte(
    clean: ServerContainer,
) -> None:
    """The rollback restores the bytes the file held, not a UTF-8 reading of them."""
    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=_drop),
        round_open=_always_open,
    )
    await run(clean, PLAYER_B, r"printf '\377\000\303\377' > /tmp/b.bin")
    await state.record(round_number=1)
    await run(clean, PLAYER_A, "cd /tmp && touch $(seq 1 60)")
    await state.record(round_number=1)
    assert "undone" in state.take_notice(user=PLAYER_A)
    assert await run(clean, PLAYER_B, "od -An -tx1 /tmp/b.bin") == " ff 00 c3 ff\n"


async def test_a_breach_undoes_only_the_breaching_player(clean: ServerContainer) -> None:
    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=_drop),
        round_open=_always_open,
    )
    await run(clean, PLAYER_A, "cd /tmp && touch $(seq 1 60)")
    await run(clean, PLAYER_B, "touch /tmp/mine")
    await state.record(round_number=1)
    assert "undone" in state.take_notice(user=PLAYER_A)
    assert state.take_notice(user=PLAYER_B) == ""
    assert await run(clean, PLAYER_B, "ls /tmp") == "mine\n"
    assert state.snapshot.nodes["/tmp/mine"].owner == PLAYER_B


async def test_nothing_is_recorded_once_the_round_is_closing(clean: ServerContainer) -> None:
    logged: list[EventBase] = []

    async def log(event: EventBase) -> None:
        logged.append(event)

    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=log),
        round_open=_never_open,
    )
    await run(clean, PLAYER_A, "touch late")
    await state.record(round_number=1)
    assert logged == []
    await state.record_closing(round_number=1)
    assert [
        event.change.path for event in logged if isinstance(event, SignalGameServerChanged)
    ] == ["/home/player_a/late"]


async def test_both_players_breaching_in_one_window_are_each_undone(
    clean: ServerContainer,
) -> None:
    state = ServerState(
        snapshot=await clean.snapshot(),
        container=clean,
        activity=ServerActivity(log_event=_drop),
        round_open=_always_open,
    )
    await run(clean, PLAYER_A, "cd /tmp && touch $(seq 1 60)")
    await run(clean, PLAYER_B, "mkfifo /tmp/p; touch /tmp/b")
    await state.record(round_number=1)
    assert "undone" in state.take_notice(user=PLAYER_A)
    assert "FIFO" in state.take_notice(user=PLAYER_B)
    assert await run(clean, PLAYER_A, "ls /tmp") == "(no output)"
    assert state.snapshot.player_nodes() == []


async def test_the_judges_container_keeps_dockers_proc_masks() -> None:
    """The players' container opens ``/proc`` to root for the ``hidepid`` mount; the judge,
    who is root, gets a container under Docker's defaults, where the masks hold."""
    judge = ServerContainer(
        users=AGENT_IDS, name=container_name(suffix="test-judge"), role=ContainerRole.JUDGE
    )
    await judge.start()
    try:
        probe = await judge.exec_as_root(
            command="test -w /proc/sysrq-trigger && echo open || echo masked",
            timeout_s=TIMEOUT,
            output_bytes=OUTPUT,
        )
        assert probe.stdout == "masked\n"
        assert (
            await judge.exec_as(
                user=PLAYER_A, command="id -u", timeout_s=TIMEOUT, output_bytes=OUTPUT
            )
        ).stdout == "1001\n"
    finally:
        await judge.stop()


async def test_a_player_cannot_reach_the_proc_paths_the_mount_opened(
    clean: ServerContainer,
) -> None:
    output = await run(clean, PLAYER_A, "test -w /proc/sysrq-trigger && echo open || echo masked")
    assert output == "masked\n"


async def test_a_container_whose_setup_fails_is_removed() -> None:
    """``useradd`` refuses a name with a space, so the setup fails after ``docker run``
    succeeded; the container must not be left behind."""
    broken = ServerContainer(
        users=("bad name",), name=container_name(suffix="test-broken"), role=ContainerRole.JUDGE
    )
    with pytest.raises(RuntimeError, match="setting up the server container failed"):
        await broken.start()
    gone = await asyncio.create_subprocess_exec(
        "docker",
        "inspect",
        broken.name,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert await gone.wait() != 0
