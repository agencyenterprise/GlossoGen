"""Experimental factors for finite shared-workspace crafting."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class SharedWorkspaceKnobs(BaseKnobs):
    """Factors of a layered crafting task solved by a team over one shared depot.

    The task is a grid of recipes ``crafter_count`` columns wide and
    ``steps_per_agent`` layers deep: each column ends in one target, each recipe
    consumes the previous layer, and ``dag_cross_edge_density`` sets how often a
    recipe also consumes a neighbouring column's output (at most
    ``dag_max_fan_in`` inputs from that layer). Work is ``crafter_count *
    steps_per_agent`` crafts and the critical path is ``steps_per_agent``.
    ``crafter_count`` may be 1, a pure chain. ``quantity_scale`` bounds each raw
    input quantity, ``dag_raw_material_count`` and ``dag_max_raw_inputs`` the raw
    items, and ``resource_slack_fraction`` adds that fraction of each raw item's
    exact need, rounded up. ``task_manifest`` replays certified tasks from a file
    instead of generating them.

    ``pool_agent_count`` agents take part (``crafter_count`` when unset; 1 is the
    single-agent baseline). Every agent is briefed with every target and the
    depot; no target or column is assigned. ``recipe_holders`` deals each recipe
    to that many agents, the hands as even as possible; unset, every agent holds
    every recipe. Any agent may run any recipe whose exact command it has.

    The team shares one pool of workspace actions, ``actions_per_witness_step``
    times the task's witness length, rounded up. ``team_token_limit`` caps the
    prompt plus completion tokens of every model response in a round, summed over
    the team; crossing it ends the round with ``team_tokens_exhausted``.
    ``uncraft_enabled`` lets ``act`` reverse a craft: ``uncraft <exact craft
    command>`` removes that recipe's output, returns its full inputs and costs one
    action.

    ``virtual_clock`` orders agents by simulated hosted-API latency instead of by
    when the inference server answered: each request costs
    ``virtual_base_latency_s`` plus its output tokens at
    ``virtual_output_tokens_per_second``, and ``wait_for_message`` timeouts count
    virtual seconds. ``craft_duration_s`` makes each accepted craft last that many
    virtual seconds: its inputs leave the depot when it starts, its output lands
    when it ends, and the crafter is busy in between while teammates act. Uncraft
    stays instantaneous.
    """

    crafter_count: int = Field(default=3, ge=1, le=12)
    steps_per_agent: int = Field(default=2, ge=1, le=20)
    quantity_scale: int = Field(default=2, ge=1, le=20)
    resource_slack_fraction: float = Field(default=0.0, ge=0, le=1)
    dag_max_fan_in: int = Field(default=2, ge=1, le=12)
    dag_cross_edge_density: float = Field(default=0.3, ge=0, le=1)
    dag_raw_material_count: int | None = Field(default=None, ge=1, le=3)
    dag_max_raw_inputs: int = Field(default=2, ge=1, le=3)
    task_manifest: str | None = None
    pool_agent_count: int | None = Field(default=None, ge=1, le=12)
    recipe_holders: int | None = Field(default=None, ge=1, le=12)
    actions_per_witness_step: float = Field(default=5.0, gt=0)
    team_token_limit: int | None = Field(default=None, gt=0)
    uncraft_enabled: bool = False
    comms_enabled: bool = True
    round_time_budget_seconds: int = -1
    seed: int = 42
    virtual_clock: bool = False
    virtual_base_latency_s: float = Field(default=1.0, ge=0, le=600)
    virtual_output_tokens_per_second: float = Field(default=50.0, gt=0)
    craft_duration_s: float = Field(default=0.0, ge=0, le=3600)

    @model_validator(mode="after")
    def validate_experiment(self) -> Self:
        """Reject impossible dimensions and accidental free communication."""
        if self.round_count < 1 or self.max_round_duration_seconds <= 0:
            raise ValueError("round count and duration must be positive")
        if self.round_time_budget_seconds < -1:
            raise ValueError("budget must be -1 (unlimited) or nonnegative")
        if self.comms_enabled and self.round_time_budget_seconds == 0:
            raise ValueError("use comms_enabled=false for zero language budget")
        if self.postmortem_enabled:
            raise ValueError("this experiment has no unmetered debrief")
        if self.craft_duration_s and not self.virtual_clock:
            raise ValueError("craft_duration_s applies only with virtual_clock=true")
        if self.recipe_holders is not None and self.recipe_holders > self.agent_count:
            raise ValueError("recipe_holders cannot exceed the number of agents")
        if self.agent_count == 1 and self.comms_enabled:
            raise ValueError("a single agent has no one to broadcast to; comms_enabled=false")
        return self

    @property
    def agent_count(self) -> int:
        """The number of agents that take part."""
        if self.pool_agent_count is None:
            return self.crafter_count
        return self.pool_agent_count
