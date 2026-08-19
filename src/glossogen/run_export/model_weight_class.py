"""Whether a run's agents ran on open-weight models, closed ones, or a mix.

Cohorts are compared along this axis constantly, and grouping on it currently
means writing the mapping again in every analysis. The research exporters derive
it by substring-matching model names (`claude`/`gpt` against `llama`/`qwen`),
which needs editing every time a family is added and silently misfiles anything
it has not heard of.

Provider is the sounder signal, and the platform already records it per agent. A
provider is a fixed set the CLI validates, and it says how the model was served:
`self-hosted` and `ollama` are weights running on hardware someone chose, and the
hosted APIs are not. That holds for a model family nobody here has run yet.

A run whose agents span both is `mixed`, which is its own condition rather than a
missing value: the cross-family pairings are the reason this column exists.

An unrecognized provider yields no class at all rather than a guess, so the cell
is empty and the run is visibly unclassified instead of quietly counted as
closed.
"""

from glossogen.server.runs.models import AgentModelSummary

OPEN_WEIGHT_PROVIDERS = frozenset({"self-hosted", "ollama"})
CLOSED_WEIGHT_PROVIDERS = frozenset({"anthropic", "openai", "google-gla"})

MODEL_CLASS_COLUMN = "model_class"

_OPEN = "open"
_CLOSED = "closed"
_MIXED = "mixed"


def model_class_of(agent_models: list[AgentModelSummary]) -> str:
    """Return ``open``, ``closed``, ``mixed``, or empty when it cannot be told."""
    open_seen = False
    closed_seen = False
    for agent in agent_models:
        if agent.provider in OPEN_WEIGHT_PROVIDERS:
            open_seen = True
            continue
        if agent.provider in CLOSED_WEIGHT_PROVIDERS:
            closed_seen = True
            continue
        return ""
    if open_seen and closed_seen:
        return _MIXED
    if open_seen:
        return _OPEN
    if closed_seen:
        return _CLOSED
    return ""
