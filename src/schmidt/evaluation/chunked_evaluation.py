"""Token-aware evaluation that uses map-reduce for large transcripts.

When a transcript exceeds the LLM context window, splits it into chunks,
extracts evidence from each chunk (map), then synthesizes a final verdict
from the collected evidence (reduce). All message text is preserved in the
map phase — no summarization or paraphrasing.
"""

import asyncio
import logging
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Conservative estimate: 1 token ≈ 3 characters.
# Actual ratio is ~3.5-4 for English, but we err on the safe side
# to avoid hitting the API limit.
_CHARS_PER_TOKEN = 3

# Leave headroom for system prompt, template text, tool schema, and output.
_OVERHEAD_TOKENS = 10_000

# Target context budget for the transcript portion of each API call.
_MAX_TRANSCRIPT_TOKENS = 150_000


class ChunkEvidence(BaseModel):
    """Observations extracted from a single transcript chunk."""

    observations: list[str] = Field(
        description=(
            "All observations relevant to the evaluation criteria. "
            "Each observation must include exact quote(s) from the transcript, "
            "identify the speaker and channel, and explain the relevance."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def ensure_observations_present(cls, data: object) -> object:
        """Handle LLMs that return empty tool arguments."""
        if isinstance(data, dict) and "observations" not in data:
            data["observations"] = []
        return data

    @field_validator("observations", mode="before")
    @classmethod
    def coerce_string_to_list(cls, v: object) -> object:
        """Handle LLMs that return a single string instead of a list."""
        if isinstance(v, str):
            return [line.strip() for line in v.split("\n") if line.strip()]
        return v


def _estimate_tokens(text: str) -> int:
    """Estimate the token count for a text string."""
    return len(text) // _CHARS_PER_TOKEN


def _chunk_transcript(transcript: str, max_chars_per_chunk: int) -> list[str]:
    """Split a transcript into chunks at line boundaries.

    Each chunk contains complete lines (never splits mid-message) and
    stays within the character budget.
    """
    lines = transcript.split("\n")
    chunks: list[str] = []
    current_lines: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > max_chars_per_chunk and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_size = 0
        current_lines.append(line)
        current_size += line_size

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


async def _run_map_phase(
    chunks: list[str],
    evaluation_criteria: str,
    system_prompt: str,
    llm_provider: LLMProvider,
) -> list[str]:
    """Extract evidence from each transcript chunk in parallel."""
    total_chunks = len(chunks)

    async def extract_from_chunk(chunk: str, chunk_number: int) -> list[str]:
        prompt = render_evaluator_prompt(
            template_name="map_evidence_user.jinja",
            template_variables={
                "evaluation_criteria": evaluation_criteria,
                "chunk": chunk,
                "chunk_number": chunk_number,
                "total_chunks": total_chunks,
            },
        )
        result = await llm_provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=prompt)],
            output_schema=ChunkEvidence,
        )
        return result.observations

    tasks = [extract_from_chunk(chunk=chunk, chunk_number=i + 1) for i, chunk in enumerate(chunks)]
    chunk_results = await asyncio.gather(*tasks)

    all_observations: list[str] = []
    for observations in chunk_results:
        all_observations.extend(observations)

    logger.info(
        "Map phase complete: %d chunks → %d observations",
        total_chunks,
        len(all_observations),
    )
    return all_observations


async def _run_reduce_phase(
    observations: list[str],
    evaluation_criteria: str,
    system_prompt: str,
    output_schema: type[T],
    llm_provider: LLMProvider,
    total_chunks: int,
) -> T:
    """Synthesize a final verdict from collected evidence."""
    numbered = "\n".join(f"{i + 1}. {obs}" for i, obs in enumerate(observations))

    prompt = render_evaluator_prompt(
        template_name="reduce_verdict_user.jinja",
        template_variables={
            "evaluation_criteria": evaluation_criteria,
            "observations": numbered,
            "total_chunks": total_chunks,
        },
    )

    return await llm_provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=prompt)],
        output_schema=output_schema,
    )


async def evaluate_transcript(
    evaluation_criteria: str,
    transcript: str,
    system_prompt: str,
    output_schema: type[T],
    llm_provider: LLMProvider,
) -> T:
    """Evaluate a transcript, using map-reduce if it exceeds the token budget.

    For small transcripts, sends a single LLM call with the full transcript.
    For large transcripts, splits into chunks, extracts evidence from each
    chunk (map phase), then synthesizes the final verdict from the collected
    evidence (reduce phase).

    Args:
        evaluation_criteria: Instructions describing what to evaluate
            (rendered from the evaluator's Jinja template, without transcript).
        transcript: The full formatted transcript to evaluate.
        system_prompt: The system-level prompt for the LLM judge.
        output_schema: Pydantic model for the structured verdict.
        llm_provider: The LLM provider to use for API calls.

    Returns:
        A validated instance of output_schema with the evaluation verdict.
    """
    total_estimated = _estimate_tokens(evaluation_criteria + transcript + system_prompt)

    if total_estimated <= _MAX_TRANSCRIPT_TOKENS + _OVERHEAD_TOKENS:
        logger.info(
            "Transcript fits in single call (~%d tokens), using direct evaluation",
            total_estimated,
        )
        prompt = render_evaluator_prompt(
            template_name="direct_evaluation_user.jinja",
            template_variables={
                "evaluation_criteria": evaluation_criteria,
                "transcript": transcript,
            },
        )
        return await llm_provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=prompt)],
            output_schema=output_schema,
        )

    criteria_overhead = _estimate_tokens(evaluation_criteria + system_prompt) + _OVERHEAD_TOKENS
    max_chunk_chars = (_MAX_TRANSCRIPT_TOKENS - criteria_overhead) * _CHARS_PER_TOKEN

    chunks = _chunk_transcript(transcript=transcript, max_chars_per_chunk=max_chunk_chars)
    logger.info(
        "Transcript too large (~%d tokens), using map-reduce with %d chunks",
        total_estimated,
        len(chunks),
    )

    observations = await _run_map_phase(
        chunks=chunks,
        evaluation_criteria=evaluation_criteria,
        system_prompt=system_prompt,
        llm_provider=llm_provider,
    )

    if not observations:
        logger.warning("Map phase produced no observations, falling back to empty evidence")

    return await _run_reduce_phase(
        observations=observations,
        evaluation_criteria=evaluation_criteria,
        system_prompt=system_prompt,
        output_schema=output_schema,
        llm_provider=llm_provider,
        total_chunks=len(chunks),
    )
