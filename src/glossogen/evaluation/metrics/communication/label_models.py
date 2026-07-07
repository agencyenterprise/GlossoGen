"""Pydantic models shared by the open-coding and feature-presence metrics.

The open-coding metric writes ``CommunicationOpenCodingSidecar`` to each
run directory; the consolidation script reads those sidecars and writes
a ``CommunicationOntology`` JSON file under
``<runs_dir>/<scenario_name>/_ontology/``; the feature-presence metric
reads the ontology and writes ``CommunicationFeaturePresenceSidecar``
back to the run directory.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

ONTOLOGY_SUBDIR_NAME = "_ontology"


def ontology_dir_for_scenario(runs_dir: Path, scenario_name: str) -> Path:
    """Return ``<runs_dir>/<scenario_name>/_ontology``.

    Single source of truth for where consolidated communication-feature
    ontology JSONs live: alongside the scenario's run directories so an
    export of the runs tree carries the ontology with it.
    """
    return runs_dir / scenario_name / ONTOLOGY_SUBDIR_NAME


class EvidenceCitation(BaseModel):
    """One round-level citation backing a free-form label."""

    round_number: int = Field(
        description="Round number whose primary-channel messages exemplify the parent label.",
    )
    quote: str = Field(
        description=(
            "Short verbatim quote (one message body) from this round on the "
            "primary channel that supports the parent label."
        ),
    )


class CommunicationLabel(BaseModel):
    """One free-form label emitted by the open-coding judge."""

    text: str = Field(
        description=(
            "Short label naming one communication-pattern feature "
            "(e.g. 'uses single-letter codes', 'positional slot ordering'). "
            "Multiple labels per run are expected."
        ),
    )
    evidence: list[EvidenceCitation] = Field(
        description=(
            "All rounds in which this feature is clearly observable on the "
            "primary channel. Cite every round with clear evidence — not "
            "just one. A pervasive feature should accumulate many citations; "
            "a one-off should accumulate exactly one. Minimum one citation."
        ),
        min_length=1,
    )


class CommunicationOpenCodingOutput(BaseModel):
    """Structured output schema enforced on the open-coding LLM call."""

    labels: list[CommunicationLabel] = Field(
        description=(
            "All free-form short labels describing communication-pattern features "
            "observed in this run's primary-channel messages. Avoid quality "
            "judgements ('uses ad-hoc abbreviations' is fine; 'uses good "
            "abbreviations' is not). Capture every distinct feature once; do "
            "not pad the list with synonyms."
        ),
    )
    explanation: str = Field(
        description=(
            "Brief overall summary of the communication-pattern features the "
            "team converged on across the run."
        ),
    )


class CommunicationOpenCodingSidecar(BaseModel):
    """Schema for the ``communication_open_coding.json`` file in each run directory."""

    run_id: str
    generated_at: datetime
    labels: list[CommunicationLabel]
    explanation: str


class OntologyCategory(BaseModel):
    """One consolidated feature category in the cross-run ontology."""

    id: str = Field(
        description=(
            "Stable snake_case identifier (e.g. 'abbreviation', "
            "'first_letter_encoding'). Used as the key in feature-presence "
            "vectors so a category never changes meaning across runs."
        ),
    )
    name: str = Field(
        description="Short human-readable name shown in reports and charts.",
    )
    description: str = Field(
        description=(
            "One- or two-sentence definition of the feature. Specific enough "
            "that the feature-presence judge can decide whether a run exhibits "
            "this feature."
        ),
    )
    synonyms: list[str] = Field(
        description=(
            "Free-form label strings from the open-coding pool that map into "
            "this category. Empty when the category was named directly without "
            "synonym evidence."
        ),
    )


class CommunicationOntology(BaseModel):
    """Versioned consolidated ontology of communication-pattern features."""

    version: str = Field(
        description=(
            "Human-chosen version string (e.g. '2026-05-11_baseline_oss'). "
            "Matches the output filename stem under "
            "``<runs_dir>/<scenario_name>/_ontology/``."
        ),
    )
    generated_at: datetime
    source_run_ids: list[str] = Field(
        description="Run ids whose open-coding sidecars fed into this consolidation.",
    )
    categories: list[OntologyCategory]


class CommunicationOntologyConsolidationOutput(BaseModel):
    """Structured output schema enforced on the consolidation LLM call.

    Mirrors :class:`CommunicationOntology` minus the bookkeeping fields
    (``version``, ``generated_at``, ``source_run_ids``) which the CLI script
    fills in itself.
    """

    categories: list[OntologyCategory]
    explanation: str = Field(
        description=(
            "Brief justification for the chosen taxonomy: which axes the "
            "categories cover and what was deliberately left out."
        ),
    )


class CategoryConfidence(BaseModel):
    """One ontology category's confidence score for a single run."""

    category_id: str = Field(
        description="Matches ``OntologyCategory.id`` from the ontology file.",
    )
    confidence: float = Field(
        description=(
            "0.0 to 1.0 — judge's confidence that this run's primary-channel "
            "messages exhibit the feature defined by this category."
        ),
        ge=0.0,
        le=1.0,
    )
    justification: str = Field(
        description=(
            "Short reasoning citing specific primary-channel evidence (or its "
            "absence) for this confidence."
        ),
    )


class CommunicationFeaturePresenceOutput(BaseModel):
    """Structured output schema enforced on the feature-presence LLM call."""

    scores: list[CategoryConfidence] = Field(
        description=(
            "Exactly one entry per ontology category, in the same order as the "
            "categories were presented. Every category gets a confidence even "
            "when the feature is plainly absent (confidence near 0)."
        ),
    )
    notes: str = Field(
        default="",
        description=(
            "Optional brief overall observations beyond the per-category "
            "scores: features that almost fit a category but didn't, or "
            "features the ontology doesn't cover yet. Empty when there is "
            "nothing extra to add — do not invent commentary."
        ),
    )


class CommunicationFeaturePresenceSidecar(BaseModel):
    """Schema for the ``communication_feature_presence.json`` file."""

    run_id: str
    ontology_version: str
    ontology_path: str
    generated_at: datetime
    scores: list[CategoryConfidence]
    notes: str
