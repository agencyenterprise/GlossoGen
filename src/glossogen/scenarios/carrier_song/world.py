"""Round state for carrier_song: each sender's executor, the open round's transmission and
decoding, and every resolved round's verdict.

A sender's executor stays in place across rounds until its author replaces it. The
noise it plays in a round is computed once per round, when the sender writes an
executor or first needs the noise, and the transmission freezes it.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.carrier_song.ids import AGENT_IDS, Role
from glossogen.scenarios.carrier_song.round_material import RoundMaterial, mix


class Transmission(NamedTuple):
    """What the sender played and what the receiver hears."""

    noise: list[int]
    recording: list[int]


class RoundOutcome(NamedTuple):
    """A resolved round."""

    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    decoded: str | None
    success: bool
    trigger: str


class _OpenRound:
    """The open round's material and what has happened in it so far."""

    def __init__(self, material: RoundMaterial) -> None:
        self.material = material
        self.noise: list[int] | None = None
        self.transmission: Transmission | None = None
        self.decoded: str | None = None
        self.releases = dict.fromkeys(AGENT_IDS, 0)


class CarrierSongWorld(ScenarioWorld):
    """Executors in place, the open round, and every resolved round's outcome."""

    def __init__(self) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._executors: dict[str, str] = {}
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, material: RoundMaterial) -> None:
        """Open a round with no noise computed, nothing transmitted and nothing decoded."""
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
        """The open round's roles, secret, song and channel noise."""
        return self._round().material

    def role_of(self, agent_id: str) -> Role:
        """What ``agent_id`` does in the open round."""
        if self.material.sender_id == agent_id:
            return Role.SENDER
        return Role.RECEIVER

    def executor_of(self, agent_id: str) -> str | None:
        """The executor ``agent_id`` has in place, or None before it wrote one."""
        return self._executors.get(agent_id)

    def place_executor(self, agent_id: str, code: str) -> None:
        """Put ``code`` in place as ``agent_id``'s executor, for this round and later ones."""
        self._executors[agent_id] = code

    @property
    def noise(self) -> list[int] | None:
        """The sender's noise on this round's song, or None before it was computed."""
        return self._round().noise

    def set_noise(self, noise: list[int]) -> None:
        """Record the sender's noise on this round's song; refused once transmitted."""
        state = self._round()
        if state.transmission is not None:
            raise ValueError("You already transmitted this round.")
        state.noise = noise

    @property
    def transmission(self) -> Transmission | None:
        """The open round's transmission, or None while the sender is still playing."""
        return self._round().transmission

    def transmit(self) -> Transmission:
        """Freeze the sender's noise and mix the recording; refused on a second call."""
        state = self._round()
        if state.transmission is not None:
            raise ValueError("You already transmitted this round.")
        noise = state.noise
        if noise is None:
            raise ValueError("The sender's noise has not been computed this round.")
        state.transmission = Transmission(
            noise=noise,
            recording=mix(
                song=state.material.song, noise=noise, channel_noise=state.material.channel_noise
            ),
        )
        return state.transmission

    @property
    def decoded(self) -> str | None:
        """The receiver's decoding, or None before it submitted one."""
        return self._round().decoded

    def decode(self, value: str) -> None:
        """Record the receiver's decoding; refused before the transmission and on a second call."""
        state = self._round()
        if state.transmission is None:
            raise ValueError(
                "Nothing has been transmitted yet. Wait with read_notifications() until your "
                "partner ends its turn."
            )
        if state.decoded is not None:
            raise ValueError("You already submitted a decoding this round.")
        state.decoded = value

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
        """Close the round: it scores when the decoding equals the secret."""
        state = self._round()
        material = state.material
        outcome = RoundOutcome(
            round_number=round_number,
            sender_id=material.sender_id,
            receiver_id=material.receiver_id,
            secret=material.secret,
            decoded=state.decoded,
            success=state.decoded == material.secret,
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
        """Rounds whose decoding matched the secret."""
        return sum(outcome.success for outcome in self._outcomes.values())
