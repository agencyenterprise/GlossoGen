"""A metric's numbers for things that are neither a round nor an agent.

Some metrics measure a run along an axis of their own. Feature presence scores one
confidence per ontology category; probe similarity scores one number per
(agent, question, cutoff); language repetition scores one factor per message. None of
those fit ``per_round`` or ``per_agent``, so they were written to a JSON file beside
the report and read by whatever plotted them.

A keyed observation is that number, with the axis it varies over named. The keys are
the metric's own: ``{"category_id": "telegraphic_ellipsis"}`` or
``{"agent_id": "field_observer", "question_id": "obs_00", "cutoff_round": "11"}``.
Nothing outside the metric knows what those names mean, which is what lets the
analysis layer group by them without knowing a single metric.

Values are read back from the sidecar rather than added to the report. The reports
already on disk cost real money to produce, and re-running evaluation on thousands of
runs to move a number from one file to another is not a migration anyone should pay
for.
"""

from pydantic import BaseModel


class KeyedObservation(BaseModel):
    """One number a metric reported, and the keys naming what it varies over.

    Keys are text because they become dimension cells, which is the same thing a
    knob or a label becomes. A numeric key (a cutoff round) is rendered, not typed:
    grouping reads it back as a number when it looks like one.
    """

    keys: dict[str, str]
    value: float
