"""``busiest_member_share`` over scripted spot_the_intersection rounds.

The rounds are played rather than built by hand, so the messages counted are the
ones the live world charged: a message after the team locks is left out.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.spot_the_intersection.evaluation.busiest_member_share_metric import (
    BusiestMemberShareMetric,
)
from tests.scenarios.spot_the_intersection.conftest import SCENARIO, TEAM_A
from tests.scenarios.spot_the_intersection.member_traffic_play import (
    measure,
    play_relay_chain,
    play_two_link_posts,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_the_share_counts_only_what_the_team_was_charged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await play_relay_chain(tmp_path=tmp_path, monkeypatch=monkeypatch)

    [measurement] = await measure(
        metric=BusiestMemberShareMetric(), played=played, tmp_path=tmp_path
    )

    assert measurement.metric_name == "busiest_member_share_team_a"
    assert measurement.score == pytest.approx(10 / 24)
    assert [
        (observation.round_number, observation.note) for observation in measurement.per_round
    ] == [(1, "viewer_a_1 sent 10 of 24 characters")]
    assert {observation.agent_id: observation.value for observation in measurement.per_agent} == {
        TEAM_A[0]: pytest.approx(10 / 24),
        TEAM_A[1]: pytest.approx(6 / 24),
        TEAM_A[2]: pytest.approx(8 / 24),
        TEAM_A[3]: 0.0,
    }


async def test_a_team_charged_for_nothing_gets_no_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Team B never speaks in the relay round, so only Team A is measured."""
    played = await play_relay_chain(tmp_path=tmp_path, monkeypatch=monkeypatch)

    measurements = await measure(
        metric=BusiestMemberShareMetric(), played=played, tmp_path=tmp_path
    )

    assert [measurement.metric_name for measurement in measurements] == [
        "busiest_member_share_team_a"
    ]


async def test_link_posts_in_a_broadcast_run_are_shared_out_by_sender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await play_two_link_posts(tmp_path=tmp_path, monkeypatch=monkeypatch)

    [measurement] = await measure(
        metric=BusiestMemberShareMetric(), played=played, tmp_path=tmp_path
    )

    assert measurement.score == pytest.approx(4 / 6)
