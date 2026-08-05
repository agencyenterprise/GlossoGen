from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.game_clock import GameClock


def _clock_with_sessions(*sessions: AgentSession) -> GameClock:
    clock = object.__new__(GameClock)
    clock._agent_sessions = {  # pyright: ignore[reportPrivateUsage]
        session.agent_id: session for session in sessions
    }
    return clock


def test_all_agents_idle_rejects_model_request_in_flight() -> None:
    first = AgentSession(agent_id="first")
    second = AgentSession(agent_id="second")
    first.is_idle = True
    second.is_idle = True
    first.model_request_in_flight = True

    clock = _clock_with_sessions(first, second)

    assert clock._all_agents_idle() is False  # pyright: ignore[reportPrivateUsage]


def test_all_agents_idle_accepts_blocked_agents_without_active_work() -> None:
    first = AgentSession(agent_id="first")
    second = AgentSession(agent_id="second")
    first.is_idle = True
    second.is_idle = True

    clock = _clock_with_sessions(first, second)

    assert clock._all_agents_idle() is True  # pyright: ignore[reportPrivateUsage]
