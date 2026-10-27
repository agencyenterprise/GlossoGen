"""Round state for signal_game_carrier: each player's executor and noise, the recording
once both have transmitted, the squares picked, and every resolved round's verdict.

A player's executor stays in place across rounds until its author replaces it. A round's
noise starts as silence for both players. It is replaced by what the executor in place
returns on the new song, when the round opens, and again by every executor its author
writes that returns usable noise. Transmitting freezes that player's noise.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.signal_game_carrier.boards import Square, colour_at
from glossogen.scenarios.signal_game_carrier.ids import AGENT_IDS
from glossogen.scenarios.signal_game_carrier.round_material import RoundMaterial
from glossogen.scenarios.signal_game_carrier.song import mix


class RoundOutcome(NamedTuple):
    """A resolved round. A player that did not pick is missing from both dicts."""

    round_number: int
    squares: dict[str, Square]
    colours: dict[str, str]
    success: bool
    trigger: str


class _OpenRound:
    """The open round's material and what has happened in it so far."""

    def __init__(self, material: RoundMaterial) -> None:
        self.material = material
        self.noise: dict[str, list[int]] = {
            agent_id: [0] * len(material.song) for agent_id in AGENT_IDS
        }
        self.executor_failure: dict[str, str | None] = dict.fromkeys(AGENT_IDS, None)
        self.transmitted: dict[str, bool] = dict.fromkeys(AGENT_IDS, False)
        self.recording: list[int] | None = None
        self.squares: dict[str, Square] = {}
        self.releases: dict[str, int] = dict.fromkeys(AGENT_IDS, 0)


class SignalGameCarrierWorld(ScenarioWorld):
    """Executors in place, the open round, and every resolved round's outcome."""

    def __init__(self) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._executors: dict[str, str] = {}
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, material: RoundMaterial) -> None:
        """Open a round with both players playing silence and nothing transmitted."""
        self._open = _OpenRound(material=material)

    @property
    def round_open(self) -> bool:
        """Whether a round has started and has not been resolved."""
        return self._open is not None

    def _round(self) -> _OpenRound:
        if self._open is None:
            raise ValueError("No round is in progress.")
        return self._open

    @property
    def material(self) -> RoundMaterial:
        """The open round's grids, song and channel noise."""
        return self._round().material

    def executor_of(self, agent_id: str) -> str | None:
        """The executor ``agent_id`` has in place, or None before it wrote one."""
        return self._executors.get(agent_id)

    def place_executor(self, agent_id: str, code: str) -> None:
        """Put ``code`` in place as ``agent_id``'s executor, for this round and later ones."""
        self._executors[agent_id] = code

    def noise_of(self, agent_id: str) -> list[int]:
        """The noise ``agent_id`` plays on this round's song now."""
        return self._round().noise[agent_id]

    def set_noise(self, agent_id: str, noise: list[int]) -> None:
        """Record ``agent_id``'s noise on this round's song; refused once it transmitted."""
        state = self._round()
        if state.transmitted[agent_id]:
            raise ValueError("You already transmitted this round.")
        state.noise[agent_id] = noise

    def executor_failure_of(self, agent_id: str) -> str | None:
        """Why ``agent_id``'s executor in place failed on this round's song, or None."""
        return self._round().executor_failure[agent_id]

    def record_executor_failure(self, agent_id: str, error: str) -> None:
        """Note that ``agent_id``'s executor failed on this song; its noise stays silence."""
        self._round().executor_failure[agent_id] = error

    def clear_executor_failure(self, agent_id: str) -> None:
        """Forget the failure once a new executor that works is in place."""
        self._round().executor_failure[agent_id] = None

    def has_transmitted(self, agent_id: str) -> bool:
        """Whether ``agent_id`` has fixed its noise for this round."""
        return self._round().transmitted[agent_id]

    def transmit(self, agent_id: str) -> list[int] | None:
        """Freeze ``agent_id``'s noise; mix and return the recording once both have.

        Returns None while the partner has still to transmit. Refused on a second call.
        """
        state = self._round()
        if state.transmitted[agent_id]:
            raise ValueError("You already transmitted this round.")
        state.transmitted[agent_id] = True
        if not all(state.transmitted.values()):
            return None
        state.recording = mix(
            song=state.material.song,
            noises=[state.noise[other] for other in AGENT_IDS],
            channel_noise=state.material.channel_noise,
        )
        return state.recording

    @property
    def recording(self) -> list[int] | None:
        """What the channel carried, or None until both players have transmitted."""
        return self._round().recording

    def square_of(self, agent_id: str) -> Square | None:
        """The square ``agent_id`` picked this round, or None."""
        return self._round().squares.get(agent_id)

    def choose(self, agent_id: str, square: Square) -> str:
        """Record ``agent_id``'s pick and return its colour; refused on a second call."""
        state = self._round()
        if agent_id in state.squares:
            raise ValueError("You already picked a square this round.")
        state.squares[agent_id] = square
        return colour_at(grid=state.material.grids[agent_id], square=square)

    @property
    def both_chose(self) -> bool:
        """Whether both players have picked a square this round."""
        return len(self._round().squares) == len(AGENT_IDS)

    def claim_release(self, agent_id: str, limit: int) -> bool:
        """Count one release of ``agent_id`` from a wait; False once ``limit`` are spent."""
        if self._open is None:
            return False
        releases = self._open.releases
        if releases[agent_id] >= limit:
            return False
        releases[agent_id] += 1
        return True

    def resolve(self, round_number: int, trigger: str) -> RoundOutcome:
        """Close the round: it scores when both squares hold the same colour."""
        state = self._round()
        colours = {
            agent_id: colour_at(grid=state.material.grids[agent_id], square=square)
            for agent_id, square in state.squares.items()
        }
        picked = [colours.get(agent_id) for agent_id in AGENT_IDS]
        outcome = RoundOutcome(
            round_number=round_number,
            squares=dict(state.squares),
            colours=colours,
            success=len(colours) == len(AGENT_IDS) and picked[0] == picked[1],
            trigger=trigger,
        )
        self._outcomes[round_number] = outcome
        self._open = None
        return outcome

    def outcome(self, round_number: int) -> RoundOutcome | None:
        """The resolved round, or None."""
        return self._outcomes.get(round_number)

    def seed_outcome(self, outcome: RoundOutcome) -> None:
        """Restore a round resolved before a fork or resume."""
        self._outcomes[outcome.round_number] = outcome

    def rounds_won(self) -> int:
        """Rounds whose two squares held the same colour."""
        return sum(outcome.success for outcome in self._outcomes.values())
