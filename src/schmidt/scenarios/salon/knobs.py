"""Configuration knobs for the Salon covert broadcast scenario.

Controls the size of the directive space, the size of the invented primer
shared by the Envoy and Confidant, the per-round adversarial pressure
imposed by the Inquisitor, whether a pair-only postmortem discussion phase
follows each round, and the seed used for primer generation and per-round
directive selection.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class SalonKnobs(BaseKnobs):
    """Configuration knobs for the Salon covert broadcast scenario.

    ``round_count`` controls how many directives are drawn in total.
    ``seed`` controls both primer generation and the per-round directive
    sequence. ``directive_space_size`` fixes the total number of possible
    directives shared by all three agents. ``primer_figure_count`` is the
    number of invented figures in the pair-shared primer and its sibling
    decoy primer given to the Inquisitor. ``inquisitor_guesses_per_round``
    is the adversarial pressure knob — more guesses per round force the
    pair to encode more covertly. ``postmortem_enabled`` toggles the
    pair-only postmortem discussion phase after each round.
    """

    postmortem_enabled: bool
    round_count: int
    seed: int
    directive_space_size: int
    primer_figure_count: int
    inquisitor_guesses_per_round: int

    @model_validator(mode="after")
    def _validate_salon_knobs(self) -> Self:
        if self.round_count < 1:
            raise ValueError(f"round_count must be >= 1 (got {self.round_count})")
        if self.directive_space_size < 2:
            raise ValueError(f"directive_space_size must be >= 2 (got {self.directive_space_size})")
        if self.primer_figure_count < self.directive_space_size:
            raise ValueError(
                f"primer_figure_count must be >= directive_space_size "
                f"(got primer_figure_count={self.primer_figure_count}, "
                f"directive_space_size={self.directive_space_size})"
            )
        if self.inquisitor_guesses_per_round < 1:
            raise ValueError(
                f"inquisitor_guesses_per_round must be >= 1 "
                f"(got {self.inquisitor_guesses_per_round})"
            )
        if self.inquisitor_guesses_per_round > self.directive_space_size:
            raise ValueError(
                f"inquisitor_guesses_per_round must be <= directive_space_size "
                f"(got inquisitor_guesses_per_round={self.inquisitor_guesses_per_round}, "
                f"directive_space_size={self.directive_space_size})"
            )
        return self
