"""A group's label glossary: what each label means.

Labels are plain strings a run carries in ``labels.json``; nothing about the string
says what the cohort behind it was for, and researchers forget. A description is the
group's recorded answer, keyed on the exact label string (``baseline_oss``,
``budget=800``), so it applies to every run carrying that label without touching any
run directory.
"""

from pydantic import BaseModel, Field


class LabelDescription(BaseModel):
    """One label and the meaning its group recorded for it."""

    label: str = Field(min_length=1)
    description: str = Field(min_length=1)


class LabelDescriptionsResponse(BaseModel):
    """Every label description the group has recorded, sorted by label."""

    descriptions: list[LabelDescription]
