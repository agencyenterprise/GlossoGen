"""The outcome log, driven where a scenario cannot reach it.

Recording a round twice, or recording it under the wrong team, produces a run
that completes and reports the wrong history. Neither shows up in an event log,
because the log is read by injection templates rather than written to the
JSONL, so a scenario run end to end cannot tell you the history is wrong.

The idempotency in particular is asked for from two directions in a real run,
and only in one order: a debrief injection records the round as it closes, then
the next boundary asks again. The reverse order never happens on the shipped
configuration, so it is driven here instead.
"""

from typing import NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog


class Outcome(NamedTuple):
    """A stand-in for whatever record a scenario builds for a finished round."""

    label: str


def log_for(*team_ids: str) -> RoundOutcomeLog[Outcome]:
    """Build an empty log for the named teams."""
    return RoundOutcomeLog(team_ids=team_ids)


def test_a_round_is_recorded_once_however_often_it_is_asked_for() -> None:
    """Two callers want the same round, and must agree on one record."""
    log = log_for("a")

    first = log.record(team_id="a", round_number=1, outcome=Outcome(label="real"))
    second = log.record(team_id="a", round_number=1, outcome=Outcome(label="duplicate"))

    assert first == Outcome(label="real")
    assert second == Outcome(label="real"), "the second caller overwrote the first"
    assert log.all_for(team_id="a") == [Outcome(label="real")]


def test_a_round_that_was_never_recorded_reads_as_absent() -> None:
    """This is the check that stops a round being recorded twice."""
    log = log_for("a")
    log.record(team_id="a", round_number=1, outcome=Outcome(label="first"))

    assert log.recorded_for(team_id="a", round_number=1) == Outcome(label="first")
    assert log.recorded_for(team_id="a", round_number=2) is None


def test_teams_keep_separate_histories() -> None:
    """Two teams run identical cases, and their outcomes must not merge."""
    log = log_for("a", "b")

    log.record(team_id="a", round_number=1, outcome=Outcome(label="a1"))
    log.record(team_id="b", round_number=1, outcome=Outcome(label="b1"))

    assert log.all_for(team_id="a") == [Outcome(label="a1")]
    assert log.all_for(team_id="b") == [Outcome(label="b1")]


def test_recording_one_team_does_not_mark_the_round_done_for_another() -> None:
    """Otherwise a two-team round would record only whichever team asked first."""
    log = log_for("a", "b")

    log.record(team_id="a", round_number=1, outcome=Outcome(label="a1"))

    assert log.recorded_for(team_id="b", round_number=1) is None


def test_the_returned_history_cannot_be_edited_through() -> None:
    """Callers render from this; a caller appending to it would corrupt the log."""
    log = log_for("a")
    log.record(team_id="a", round_number=1, outcome=Outcome(label="first"))

    log.all_for(team_id="a").append(Outcome(label="smuggled"))

    assert log.all_for(team_id="a") == [Outcome(label="first")]


def test_rounds_recorded_out_of_order_keep_their_own_records() -> None:
    """A resumed run replays rounds it did not play, and must not confuse them."""
    log = log_for("a")

    log.record(team_id="a", round_number=2, outcome=Outcome(label="second"))
    log.record(team_id="a", round_number=1, outcome=Outcome(label="first"))

    assert log.recorded_for(team_id="a", round_number=1) == Outcome(label="first")
    assert log.recorded_for(team_id="a", round_number=2) == Outcome(label="second")
