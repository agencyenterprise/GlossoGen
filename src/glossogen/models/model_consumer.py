"""Something in a run that will call a model, and what it will call.

Agents are the obvious ones. A scenario that judges its own rounds calls a
model of its own, under a provider its knobs name and nothing else does, so
the two are checked together and reported the same way.

Lives apart from the check that reads it, because the scenario contract
declares its judges in these terms and the check imports the contract.
"""

from typing import NamedTuple


class ModelConsumer(NamedTuple):
    """One caller of a model within a run.

    ``name`` is what the run calls it, an agent id or a description of the
    scenario's own use, and appears in the message when its model cannot be
    reached.
    """

    name: str
    model: str
    provider: str
