"""Configuration knobs for the Veyru stabilization scenario.

Controls the per-round time budget, case shuffling seed, round count,
postmortem discussion, two-team mode, observer swap timing, swap
announcement, post-swap postmortem availability, intern observer mode, and
the LLM judge.
"""

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class VeyruKnobs(BaseKnobs):
    """Configuration knobs for the Veyru stabilization scenario.

    ``round_time_budget_seconds`` is the fixed per-round budget applied to
    every case: every character sent on the comm link costs one simulated
    second, and if the running total exceeds the budget the Veyru
    collapses. ``seed`` controls the random shuffle of failure motifs into
    round cases. ``postmortem_enabled``
    controls whether a shared discussion phase follows each round.
    ``two_teams`` is an opt-in toggle that runs two isolated observer/
    stabilization engineer teams in parallel on identical cases each round.
    ``swap_round`` (only meaningful when ``two_teams`` is true) is the last
    round before the two teams' field observers are swapped between teams.
    ``announce_swap`` controls whether agents are explicitly notified that
    a swap happened (both in their next-round injection and via a channel
    system update). ``postmortem_after_swap`` controls whether the
    postmortem channel remains available after the swap (reused by intern
    mode to control intern postmortem access after takeover).
    ``postmortem_disabled_at_start`` disables the postmortem phase from
    the very first round; used by the replace-agent flow to drop the
    postmortem channel for the rest of a resumed simulation.
    ``intern_enabled`` is an opt-in toggle (single-team only) that adds a
    silent intern observer who joins the link at ``intern_join_round``,
    observes the field observer work, then replaces the field observer at
    ``intern_takeover_round``. When intern mode is enabled, every
    ``stabilize_veyru`` tool call is broadcast to the entire link channel
    (args + result) so the intern can observe the protocol.
    ``judge_model`` and ``judge_provider`` specify the LLM used to evaluate
    whether stabilization actions match the Veyru's needs.
    ``channel_noise_level`` is the per-character drop probability applied
    to messages on the link channel(s) only (postmortem stays clean). At
    ``0.0`` the channel is lossless (current behavior); at ``1.0`` every
    character is dropped. Dropped characters are replaced with ``_`` so
    agents can see where loss occurred.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    round_count: int
    round_time_budget_seconds: int
    seed: int
    two_teams: bool
    swap_round: int | None
    announce_swap: bool
    postmortem_after_swap: bool
    postmortem_disabled_at_start: bool = False
    intern_enabled: bool
    intern_join_round: int | None
    intern_takeover_round: int | None
    channel_noise_level: float

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> "VeyruKnobs":
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_swap_round(self) -> "VeyruKnobs":
        if self.swap_round is None:
            return self
        if not self.two_teams:
            raise ValueError("swap_round requires two_teams=true")
        if self.swap_round < 1 or self.swap_round >= self.round_count:
            raise ValueError(
                f"swap_round must satisfy 1 <= swap_round < round_count "
                f"(got swap_round={self.swap_round}, round_count={self.round_count})"
            )
        return self

    @model_validator(mode="after")
    def _validate_postmortem_after_swap(self) -> "VeyruKnobs":
        if self.postmortem_after_swap and not self.postmortem_enabled:
            raise ValueError(
                "postmortem_after_swap=true requires postmortem_enabled=true "
                "(the post-swap knob controls how the postmortem channel is handled "
                "across the boundary, so it has no effect when the postmortem is off)."
            )
        return self

    @model_validator(mode="after")
    def _validate_intern_mode(self) -> "VeyruKnobs":
        if not self.intern_enabled:
            if self.intern_join_round is not None or self.intern_takeover_round is not None:
                raise ValueError(
                    "intern_join_round and intern_takeover_round must be null "
                    "when intern_enabled=false"
                )
            return self
        if self.two_teams:
            raise ValueError("intern_enabled=true requires two_teams=false")
        if self.intern_join_round is None or self.intern_takeover_round is None:
            raise ValueError(
                "intern_enabled=true requires both intern_join_round and "
                "intern_takeover_round to be set"
            )
        if self.intern_join_round < 1:
            raise ValueError(f"intern_join_round must be >= 1 (got {self.intern_join_round})")
        if self.intern_takeover_round <= self.intern_join_round:
            raise ValueError(
                f"intern_takeover_round must be greater than intern_join_round "
                f"(got intern_join_round={self.intern_join_round}, "
                f"intern_takeover_round={self.intern_takeover_round})"
            )
        if self.intern_takeover_round > self.round_count:
            raise ValueError(
                f"intern_takeover_round must be <= round_count "
                f"(got intern_takeover_round={self.intern_takeover_round}, "
                f"round_count={self.round_count})"
            )
        return self
