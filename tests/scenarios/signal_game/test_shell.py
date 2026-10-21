"""A player's shell on the shared server, driven directly with a fixed clock and sleeper."""

import asyncio
from datetime import UTC, datetime
from typing import NamedTuple

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.events import SignalGameServerChanged
from glossogen.scenarios.signal_game.ids import AGENT_IDS, PLAYER_A, PLAYER_B, WrittenTextKind
from glossogen.scenarios.signal_game.judged_text import WrittenText
from glossogen.scenarios.signal_game.server_activity import ServerActivity, Sleeper
from glossogen.scenarios.signal_game.server_changes import ServerChangeKind
from glossogen.scenarios.signal_game.server_shell_fs import ServerShellFs
from glossogen.scenarios.signal_game.shared_server import SharedServer
from glossogen.scenarios.signal_game.shell_session import ShellSession, WaitBudget, build_commands

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
ROUND = 1


class Server(NamedTuple):
    """A server, its activity, both players' shells, and what the run recorded."""

    server: SharedServer
    activity: ServerActivity
    a: ShellSession
    b: ShellSession
    events: list[EventBase]
    slept: list[float]
    open_rounds: set[int]


def start(max_sleep_seconds: float, sleeper: Sleeper | None) -> Server:
    server = SharedServer(users=AGENT_IDS, at=AT)
    events: list[EventBase] = []
    slept: list[float] = []
    open_rounds = {ROUND}

    async def log(event: EventBase) -> None:
        events.append(event)

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    activity = ServerActivity(
        server=server, log_event=log, round_open=lambda number: number in open_rounds
    )

    def shell(user: str) -> ShellSession:
        view = ServerShellFs(server=server, user=user, observer=activity, clock=lambda: AT)
        budget = WaitBudget(seconds_per_command=max_sleep_seconds)
        chosen: Sleeper = record_sleep
        if sleeper is not None:
            chosen = sleeper
        return ShellSession(
            view=view,
            commands=build_commands(
                view=view, activity=activity, users=AGENT_IDS, wait_budget=budget, sleeper=chosen
            ),
            wait_budget=budget,
            output_char_limit=4000,
        )

    return Server(
        server=server,
        activity=activity,
        a=shell(user=PLAYER_A),
        b=shell(user=PLAYER_B),
        events=events,
        slept=slept,
        open_rounds=open_rounds,
    )


def plain() -> Server:
    return start(max_sleep_seconds=30, sleeper=None)


async def run(shell: ShellSession, command: str) -> str:
    return await shell.run(command=command, round_number=ROUND)


async def test_a_file_one_player_writes_is_listed_as_its_and_read_by_the_other() -> None:
    server = plain()
    assert await run(shell=server.a, command="echo hi > /tmp/x") == "(no output)"
    assert await run(shell=server.b, command="cat /tmp/x") == "hi\n"
    listing = await run(shell=server.b, command="ls -l /tmp")
    assert listing == "total 4\n-rw-r--r-- 1 player_a player_a 3 Oct 20 12:00 x\n"


async def test_chmod_closes_a_file_to_the_partner() -> None:
    server = plain()
    await run(shell=server.a, command="echo hi > note; chmod 600 note")
    denied = await run(shell=server.b, command="cat /home/player_a/note")
    assert "Permission denied" in denied
    assert "[exit status 1]" in denied


async def test_symbolic_and_sticky_modes_show_as_ls_prints_them() -> None:
    server = plain()
    output = await run(
        shell=server.a, command="printf '' > f; chmod u+x,go-r f; mkdir d; chmod 1777 d; ls -l"
    )
    assert "-rwx------ 1 player_a player_a    0 Oct 20 12:00 f" in output
    assert "drwxrwxrwt 2 player_a player_a 4096 Oct 20 12:00 d" in output


async def test_only_the_owner_changes_a_mode_and_removes_from_tmp() -> None:
    server = plain()
    await run(shell=server.a, command="touch /tmp/f")
    assert "Operation not permitted" in await run(shell=server.b, command="chmod 777 /tmp/f")
    assert "Operation not permitted" in await run(shell=server.b, command="rm /tmp/f")


async def test_a_glob_skips_a_home_the_player_may_not_list() -> None:
    server = plain()
    await run(shell=server.a, command="chmod 700 ~; touch secret")
    await run(shell=server.b, command="touch mine")
    assert await run(shell=server.b, command="echo /home/*/*") == "/home/player_b/mine\n"


async def test_a_player_appends_to_a_file_it_may_write_but_not_read() -> None:
    server = plain()
    await run(shell=server.a, command="printf 'zero\\n' > /tmp/box; chmod 622 /tmp/box")
    assert await run(shell=server.b, command="echo one >> /tmp/box") == "(no output)"
    assert "Permission denied" in await run(shell=server.b, command="cat /tmp/box")
    assert await run(shell=server.a, command="cat /tmp/box") == "zero\none\n"


async def test_stat_shows_the_owner_mode_and_both_times() -> None:
    server = plain()
    await run(shell=server.a, command="touch -d '2026-01-02 03:04:05' f; chmod 640 f")
    output = await run(shell=server.b, command="stat -c '%U %a %Y %Z %n' /home/player_a/f")
    assert output == f"player_a 640 1767323045 {int(AT.timestamp())} /home/player_a/f\n"


async def test_sleep_draws_on_the_command_lines_wait_budget() -> None:
    server = plain()
    output = await run(shell=server.a, command="sleep 10; sleep 25")
    assert server.slept == [10.0, 20.0]
    assert "sleep: waiting is capped at 30 seconds per command line" in output
    await run(shell=server.a, command="sleep 5")
    assert server.slept == [10.0, 20.0, 5.0]


async def test_inotifywait_returns_on_the_partners_change() -> None:
    never = asyncio.Event()

    async def until_cancelled(seconds: float) -> None:
        _ = seconds
        await never.wait()

    server = start(max_sleep_seconds=30, sleeper=until_cancelled)
    waiting = asyncio.ensure_future(run(shell=server.b, command="inotifywait -t 20 /tmp"))
    while not server.activity._watchers:  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(0)
    await run(shell=server.a, command="echo x > /tmp/y")
    assert await waiting == "/tmp/ MODIFY y\n"


async def test_a_command_line_that_outlasts_its_round_stops_without_changing_anything() -> None:
    server = plain()
    server.open_rounds.clear()
    output = await run(shell=server.a, command="echo x > /tmp/f")
    assert "round 1 ended while this command line ran" in output
    assert not server.server.exists(user=PLAYER_A, path="/tmp/f")


async def test_command_substitution_in_a_subscript_is_refused() -> None:
    server = plain()
    output = await run(shell=server.a, command="a=(1 2); echo ${a[$(echo 0)]}")
    assert "unsupported syntax" in output


async def test_copies_and_moves_keep_the_mode_cp_would_give() -> None:
    server = plain()
    output = await run(
        shell=server.a, command="printf 1 > f; chmod 600 f; cp f g; mv g h; ls -l f h"
    )
    assert "-rw------- 1 player_a player_a 1 Oct 20 12:00 f" in output
    assert "-rw------- 1 player_a player_a 1 Oct 20 12:00 h" in output


async def test_every_change_is_logged_for_replay() -> None:
    server = plain()
    await run(shell=server.a, command="mkdir d; printf 1 > d/f; chmod 600 d/f; rm -r d")
    logged = [event for event in server.events if isinstance(event, SignalGameServerChanged)]
    assert [event.change.kind for event in logged] == [
        ServerChangeKind.MKDIR,
        ServerChangeKind.WRITE,
        ServerChangeKind.CHMOD,
        ServerChangeKind.REMOVE,
    ]
    assert {event.agent_id for event in logged} == {PLAYER_A}


async def test_the_shell_names_its_users() -> None:
    server = plain()
    assert await run(shell=server.b, command="whoami") == "player_b\n"
    assert await run(shell=server.b, command="id -un player_a") == "player_a\n"
    assert await run(shell=server.b, command="users") == "player_a player_b\n"
    assert "player_b:x:1002:1002" in await run(shell=server.b, command="cat /etc/passwd")


async def test_a_refusal_names_its_path_once() -> None:
    server = plain()
    await run(shell=server.a, command="touch /tmp/f")
    assert await run(shell=server.b, command="rm /tmp/f") == (
        "rm: cannot remove '/tmp/f': Operation not permitted\n[exit status 1]\n"
    )
    redirected = await run(shell=server.b, command="echo x > /home/player_a/f")
    assert "bash: /home/player_a/f: Permission denied\n" in redirected


async def test_names_spelled_across_nodes_reach_the_judge_whole() -> None:
    server = plain()
    await run(shell=server.a, command="touch r e d; mkdir -p q/u; touch /tmp/z")
    listing = WrittenText(
        kind=WrittenTextKind.NAMES, path="/", author=PLAYER_A, text="r\ne\nd\nq\nq/u\nz"
    )
    assert listing in server.activity.texts_to_judge()


async def test_a_text_the_judge_passed_is_not_shown_to_it_again() -> None:
    server = plain()
    await run(shell=server.a, command="printf 1011 > /tmp/x")
    first = server.activity.texts_to_judge()
    server.activity.pass_texts(texts=first)
    assert server.activity.texts_to_judge() == []
    server.activity.start_round()
    await run(shell=server.a, command="printf 1011 > /tmp/x; printf 0 > /tmp/y")
    assert [text.text for text in server.activity.texts_to_judge()] == ["y", "0", "x\ny"]


async def test_date_who_and_w_print_utc() -> None:
    server = plain()
    assert await run(shell=server.a, command="date +%Z") == "UTC\n"
    assert await run(shell=server.a, command="who") == (
        "player_a pts/0        2026-10-20 12:00\nplayer_b pts/1        2026-10-20 12:00\n"
    )
    w = await run(shell=server.a, command="w")
    assert w.startswith(" 12:00:00 up 0 min,  2 users,")
