"""What the scenario keeps of a round's command lines for the judge."""

from datetime import UTC, datetime

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.ids import AGENT_IDS, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_server.ids import WrittenTextKind
from glossogen.scenarios.signal_game_server.server_activity import (
    JUDGED_OUTPUT_CHARS,
    OUTPUT_NOT_RETURNED,
    ServerActivity,
)
from glossogen.scenarios.signal_game_server.server_snapshot import empty_snapshot


async def ignore(event: EventBase) -> None:
    _ = event


def commands_judged(activity: ServerActivity) -> list[tuple[str, str, str, str]]:
    snapshot = empty_snapshot(users=AGENT_IDS, at=datetime.now(tz=UTC))
    return [
        (text.author, text.path, text.text, text.output)
        for text in activity.texts_to_judge(snapshot=snapshot)
        if text.kind is WrittenTextKind.COMMAND
    ]


def test_a_command_line_still_running_reads_as_not_returned() -> None:
    activity = ServerActivity(log_event=ignore)
    activity.record_command(author=PLAYER_A, number=1, command="ls /tmp")
    activity.record_command(author=PLAYER_B, number=1, command="sleep 30")
    activity.record_command_output(author=PLAYER_A, number=1, output="(no output)")

    assert commands_judged(activity=activity) == [
        (PLAYER_A, "run_command 1", "ls /tmp", "(no output)"),
        (PLAYER_B, "run_command 1", "sleep 30", OUTPUT_NOT_RETURNED),
    ]


def test_the_judge_reads_the_end_of_a_long_output() -> None:
    activity = ServerActivity(log_event=ignore)
    activity.record_command(author=PLAYER_A, number=1, command="seq 100000")
    output = "x" * (JUDGED_OUTPUT_CHARS * 3) + "[exit status 1]\n"
    activity.record_command_output(author=PLAYER_A, number=1, output=output)

    [(_, _, _, judged)] = commands_judged(activity=activity)
    assert judged.startswith("[earlier output cut]\n")
    assert judged.endswith("[exit status 1]\n")
    assert len(judged) == len("[earlier output cut]\n") + JUDGED_OUTPUT_CHARS


def test_an_output_after_the_round_was_forgotten_is_dropped() -> None:
    activity = ServerActivity(log_event=ignore)
    activity.record_command(author=PLAYER_A, number=1, command="sleep 30")
    activity.start_round()
    activity.record_command_output(author=PLAYER_A, number=1, output="(no output)")

    assert commands_judged(activity=activity) == []
