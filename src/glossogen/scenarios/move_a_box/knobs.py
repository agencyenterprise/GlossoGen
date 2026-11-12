"""Knobs for move_a_box: the floor, the step budget, what the readout shows and how it is paced."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.runtime.scenario_tool import SCENARIO_TOOL_TIMEOUT_SECONDS
from glossogen.scenario_contract.base_knobs import BaseKnobs
from glossogen.scenarios.move_a_box.ids import (
    BAY_LETTERS,
    BAY_SYMBOLS,
    MAX_CRATES_EACH,
    MAX_OPERATORS,
    MAX_TARGETS_PER_ROUND,
    BayIdentity,
    CrateStart,
)

MIN_BAY_COUNT = 3
"""Fewest bays a floor can hold: one shared and one private to each of two operators."""


class MoveABoxKnobs(BaseKnobs):
    """The factors of one move_a_box run.

    ``operator_count`` is how many operators run, each on a floor of its own,
    and ``crates_each`` is how many crates each of them works at once. Crates
    are matched by slot: every operator's first crate has to meet on one bay,
    every operator's second on another, and a bay takes one crate per floor, so
    the slots cannot share a destination. The floor is ``grid_size`` squares on a side and holds
    ``bay_count`` bays, the same squares for every operator. ``steps_per_round``
    caps the actions one operator takes in a round. Nothing an operator reads
    states that cap, so set high it is a backstop and set near the distance to a
    bay it is a budget that makes an action spent on the reading cost a delivery.

    The depot assigns each operator ``bays_allowed_each`` bays, and a crate
    left on a bay the depot did not assign scores nothing. ``bays_differ``
    decides how far the two lists overlap: on, exactly one bay is on both and
    the rest of each list is that operator's alone, so the bay both may use is
    one neither can name alone. Off, both get the same list and hold the same
    information: the control.

    ``bay_identity`` decides what tells the operators which bay is which. Under
    ``square`` the bays stand on the same squares of every floor and a bay is
    named by its square. Under ``symbol`` and ``letter`` a floor holds only the
    bays its operator was assigned, each marked with a symbol or a letter, on
    squares no other floor's bays use, so only the mark says which bay is
    which. Bay ``n`` carries the ``n``-th symbol or letter, and an operator only
    ever sees the marks on its own floor.

    ``bay_identity_from_round`` switches the identity partway through a run:
    ``{6: symbol}`` plays from round 6 on under ``symbol``, and the rounds
    before it under ``bay_identity``. The briefing of the round a switch takes
    effect announces it. A switch goes between ``symbol`` and ``letter`` only,
    since square bays lay out every floor differently.

    ``targets_per_round`` is how many targets a round holds. Each target
    assigns every operator a list of bays with one bay on every list, as a
    round does. Once every operator has left its crate, the next target's bays
    are drawn on the same floor, away from where the crates stand, and each
    operator moves its crate on from there. Each target scores on its own, and
    a round succeeds only when every target matched. Above 1 it needs
    ``crates_each`` at 1.

    ``pallet_density`` is the share of open squares holding a pallet, drawn
    separately for each operator. Pallets never close a bay off, they only make
    a crate go around, so at 0.0 the floors are clear and every bay is the same
    walk for both.

    ``partner_readout`` puts the other crate's line in the readout. Off, an
    operator sees only its own crate, which is the condition where nothing can
    cross.

    ``crate_start`` places the crates: on the same fixed corner every round, on
    one square drawn per round, or on a square drawn per operator. A fixed
    corner makes every bay the same known distance away in every round, which
    lets an operator read the other's travel out of its temperature without any
    agreed code; drawing the square changes that geometry each round.

    ``partner_bay_disclosed`` names the bay the other crate was left on in the
    round result. Off, a round that did not match reports only that the other
    crate went somewhere else, so an operator learns whether it agreed and
    nothing more.

    ``partner_disclosed`` tells each operator in its briefing that another
    operator is working and that matching bays scores. Off, the system prompt
    says nothing about either, and the first round's result is where both can
    first be inferred.

    ``readout_history`` shows every reading taken so far this round rather than
    the current one, which marks where one reading ends and the next begins.

    ``decoy_readings`` puts the crate masses and the floor humidity in the
    readout beside the temperatures. Neither answers to anything an operator
    does.

    ``thermal_table_disclosed`` states in the system prompt what each action
    does to the reading, instead of leaving it to be found.

    ``channel_disclosed`` tells each operator that its actions move its crate's
    reading, that the other operator reads it, and to use it to agree on a bay.
    It gives no encoding, so the operators still have to build one. On, a run
    measures whether a pair can invent a protocol over a channel it has been
    handed; off, whether it finds the channel at all.

    ``notepad_enabled`` offers a private note the operator writes and reads back,
    logged and never shown to the other operator.

    ``action_reasoning`` makes every action carry one sentence on why, logged
    and never shown to the other operator.

    ``batched_actions`` offers one ``act`` tool in place of ``haul``,
    ``stand_by``, ``pack_ice`` and ``finish``. ``act`` takes a list of actions,
    as long as the operator likes, and applies it in order, as far as the floor
    takes it, before any other operator is woken, so an operator can lay down a
    whole run of readings before anyone reads one of them. Off, every action is
    a call of its own and the others can read the reading after each.

    ``lockstep`` holds an operator's action open until the other has acted, so
    the two readings advance together. Under ``batched_actions`` the hold comes
    once, after the list. ``lockstep_timeout_seconds`` bounds that
    hold, and a hold that expires returns the readout unchanged.

    ``virtual_clock`` paces the operators by simulated time instead: each model
    request costs ``virtual_base_latency_s`` plus its output tokens at
    ``virtual_output_tokens_per_second``, and the operators' responses are
    released in that order, whatever order their providers answered in. It
    needs ``lockstep`` off. ``read_notifications`` timeouts count virtual
    seconds. ``step_duration_s`` makes every action that spends a step last that
    many virtual seconds and land when it ends, so an operator working through a
    list is busy while the others act and read its readings as they land. A
    finish takes no time. ``virtual_list_cost_fixed`` charges each ``act``
    list ``virtual_list_cost_s`` whatever its length, in place of the list's
    own tokens, which are estimated from its length; the rest of the response
    is charged by its tokens as before.

    ``describe_protocol_at_end`` has the runner send each operator one more
    message once the run has completed: whether it and the others settled on
    any way of telling each other something, and if so to describe it. The
    operator answers in text with no tool call allowed, and nothing reaches it
    before the last round is over, so the rounds play as they would without it.
    """

    operator_count: int = Field(ge=2, le=MAX_OPERATORS)
    crates_each: int = Field(ge=1, le=MAX_CRATES_EACH)
    targets_per_round: int = Field(ge=1, le=MAX_TARGETS_PER_ROUND)
    grid_size: int = Field(ge=4, le=12)
    bay_count: int = Field(ge=MIN_BAY_COUNT, le=min(len(BAY_SYMBOLS), len(BAY_LETTERS)))
    bays_allowed_each: int = Field(ge=2, le=8)
    steps_per_round: int = Field(ge=4, le=500)
    bays_differ: bool
    bay_identity: BayIdentity
    bay_identity_from_round: dict[int, BayIdentity]
    pallet_density: float = Field(ge=0.0, le=0.4)
    crate_start: CrateStart
    partner_readout: bool
    partner_disclosed: bool
    partner_bay_disclosed: bool
    readout_history: bool
    decoy_readings: bool
    thermal_table_disclosed: bool
    channel_disclosed: bool
    notepad_enabled: bool
    action_reasoning: bool
    batched_actions: bool
    lockstep: bool
    lockstep_timeout_seconds: float = Field(gt=0.0, lt=SCENARIO_TOOL_TIMEOUT_SECONDS)
    virtual_clock: bool
    virtual_base_latency_s: float = Field(ge=0, le=600)
    virtual_output_tokens_per_second: float = Field(gt=0)
    step_duration_s: float = Field(ge=0, le=3600)
    virtual_list_cost_fixed: bool
    virtual_list_cost_s: float = Field(ge=0, le=600)
    describe_protocol_at_end: bool
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse knob combinations a run cannot play; each error names the one it refused."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        floor_bays = self.bay_count
        if self.bay_identity.is_marked():
            floor_bays = self.bays_allowed_each
        if floor_bays * 4 > self.grid_size * self.grid_size:
            raise ValueError(
                f"grid_size is too small for {floor_bays} bays on one floor under "
                f"bay_identity={self.bay_identity.value}: bays stand apart, so a "
                f"{self.grid_size}x{self.grid_size} floor does not hold {floor_bays} of them"
            )
        for start, switched in self.bay_identity_from_round.items():
            if not 2 <= start <= self.round_count:
                raise ValueError(
                    f"bay_identity_from_round switches at round {start}: a switch takes effect "
                    f"at a round between 2 and round_count={self.round_count}"
                )
            if switched.is_marked() != self.bay_identity.is_marked():
                raise ValueError(
                    "bay_identity_from_round switches only between symbol and letter: square "
                    "bays put every bay on every floor, which no briefing can announce midway"
                )
        if self.targets_per_round > 1 and self.crates_each > 1:
            raise ValueError(
                "targets_per_round above 1 needs crates_each=1: a target starts where each "
                "operator's crate was left, and one crate stands on one square"
            )
        if self.bays_allowed_each < self.crates_each:
            raise ValueError(
                f"bays_allowed_each must be at least crates_each={self.crates_each}: every "
                "operator's list has to hold a bay for each of its crates"
            )
        needed = self.crates_each + self.operator_count * (
            self.bays_allowed_each - self.crates_each
        )
        if self.bays_differ and self.bay_count < needed:
            raise ValueError(
                f"bay_count must be at least {needed} for {self.operator_count} operators at "
                f"bays_allowed_each={self.bays_allowed_each} and crates_each={self.crates_each} "
                "when bays_differ (one bay on every list per crate slot, the rest private), or "
                "the lists cannot share exactly those bays and keep the others to themselves"
            )
        if self.bay_count < self.bays_allowed_each:
            raise ValueError("bays_allowed_each cannot exceed bay_count")
        if self.steps_per_round < self.grid_size:
            raise ValueError(
                "steps_per_round must be at least grid_size, or no bay is within the budget"
            )
        if self.channel_disclosed and not (self.partner_readout and self.partner_disclosed):
            raise ValueError(
                "channel_disclosed needs partner_readout and partner_disclosed: telling an "
                "operator to signal to someone it is not told about, over a reading it cannot "
                "see, describes a run that does not exist"
            )
        if self.partner_disclosed and not self.partner_readout:
            raise ValueError(
                "partner_disclosed needs partner_readout: telling an operator its bay must "
                "match while showing it nothing of the other crate leaves it guessing"
            )
        if self.virtual_clock and self.lockstep:
            raise ValueError(
                "virtual_clock needs lockstep off: a held action keeps its operator executing "
                "on the clock, and the clock releases no other operator's response meanwhile"
            )
        if self.step_duration_s and not self.virtual_clock:
            raise ValueError("step_duration_s applies only with virtual_clock=true")
        if self.virtual_list_cost_fixed and not (self.virtual_clock and self.batched_actions):
            raise ValueError(
                "virtual_list_cost_fixed needs virtual_clock and batched_actions: it prices "
                "the list of an act call on the clock"
            )
        if self.virtual_list_cost_s and not self.virtual_list_cost_fixed:
            raise ValueError("virtual_list_cost_s applies only with virtual_list_cost_fixed=true")
        return self

    def bay_identity_of(self, round_number: int) -> BayIdentity:
        """The identity round ``round_number`` plays under: the last switch at or before it."""
        identity = self.bay_identity
        for start, switched in sorted(self.bay_identity_from_round.items()):
            if start <= round_number:
                identity = switched
        return identity
