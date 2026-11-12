"""``message_routes`` over scripted spot_the_intersection rounds.

A direct message is one route, to its recipient; a link post is a route to every
teammate. Messages after the team locks are left out.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.spot_the_intersection.evaluation.message_routes_metric import (
    MessageRoutesMetric,
)
from tests.scenarios.spot_the_intersection.conftest import SCENARIO
from tests.scenarios.spot_the_intersection.member_traffic_play import (
    measure,
    play_relay_chain,
    play_two_link_posts,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_a_relay_chain_takes_one_route_per_hop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await play_relay_chain(tmp_path=tmp_path, monkeypatch=monkeypatch)

    [measurement] = await measure(metric=MessageRoutesMetric(), played=played, tmp_path=tmp_path)

    assert measurement.metric_name == "message_routes_team_a"
    assert measurement.score == pytest.approx(3.0)
    assert measurement.per_round[0].note == (
        "viewer_a_1→viewer_a_2, viewer_a_2→viewer_a_3, viewer_a_3→viewer_a_4"
    )
    assert [observation.value for observation in measurement.per_agent] == [1.0, 1.0, 1.0, 0.0]


async def test_a_link_post_reaches_every_teammate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await play_two_link_posts(tmp_path=tmp_path, monkeypatch=monkeypatch)

    [measurement] = await measure(metric=MessageRoutesMetric(), played=played, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(6.0)
    assert [observation.value for observation in measurement.per_agent] == [3.0, 3.0, 0.0, 0.0]
