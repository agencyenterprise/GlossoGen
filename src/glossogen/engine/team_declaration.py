"""What a scenario's teams, channels and roles are, stated as data.

A scenario built on the round engine describes its structure instead of
building it. The engine derives from these the things a scenario currently
writes by hand: the ``AgentConfig`` list, the ``Channel`` list, the display-name
maps, which channels carry the task, and which carry the debrief.

Nothing here has a default. A field with a default is a question the author can
answer by silence, and answering by silence is how a scenario ends up with no
debrief phase, no budget, or a task channel nobody metered. Constructing a
declaration means answering every question; forgetting one is a type error, not
a run that completes and reports numbers.

For the same reason there are no ``Optional`` fields. "This team has no debrief"
is stated as ``NoDebrief()``, not as ``None``, so the absence is something the
author wrote rather than something they omitted.
"""

from typing import Literal, NamedTuple


class NoDebrief(NamedTuple):
    """This team holds no post-round discussion."""

    kind: Literal["none"] = "none"


class Debrief(NamedTuple):
    """This team discusses each round on its own channel once the phase opens.

    ``channel_id`` is the id the transcript and the metrics see; ``name`` is the
    channel's name in the run; ``display_name`` is what the agents are told to
    call it, which is what a rejection message names when the phase is shut.
    """

    channel_id: str
    name: str
    display_name: str
    kind: Literal["debrief"] = "debrief"


DebriefPolicy = NoDebrief | Debrief


class TaskChannel(NamedTuple):
    """The channel a team does its work on.

    This is the channel the engine meters against the round budget, corrupts
    when channel noise is on, and shuts while the debrief phase is open. Those
    three behaviours follow from being the task channel, so a scenario cannot
    wire them to the wrong channel or forget one of them.
    """

    channel_id: str
    name: str
    display_name: str


class RoleSpec(NamedTuple):
    """One agent's identity, prompt and reach.

    ``joins_debrief`` is stated per role because a team can hold a debrief that
    not every member attends: veyru's intern sits on the comm link from the
    round it joins but only reaches the discussion channel under one knob
    combination.

    ``starts_as_member`` separates two facts a role declaration would otherwise
    conflate. Which channels a role *reaches* is fixed at agent construction and
    shapes its system prompt. Whether it is *in* the channel's roster on round
    one is separate, and a role that arrives mid-run is configured for its
    channel from the start while an intervention adds it to the roster later.
    Collapsing the two puts a not-yet-arrived agent in the room from round one,
    reading traffic it was never meant to see.
    """

    agent_id: str
    role_name: str
    system_template: str
    tool_names: tuple[str, ...]
    joins_debrief: bool
    starts_as_member: bool


class TeamSpec(NamedTuple):
    """A team: one task channel, a debrief policy, and the roles that staff it.

    A single-team scenario declares one of these. Two competing teams declare
    two, and the engine meters, judges and reports each independently, which is
    what ``team_id`` keys.
    """

    team_id: str
    task: TaskChannel
    debrief: DebriefPolicy
    roles: tuple[RoleSpec, ...]

    def channel_ids_for(self, role: RoleSpec) -> tuple[str, ...]:
        """Return the channels ``role`` belongs to, task channel first."""
        if isinstance(self.debrief, Debrief) and role.joins_debrief:
            return (self.task.channel_id, self.debrief.channel_id)
        return (self.task.channel_id,)
