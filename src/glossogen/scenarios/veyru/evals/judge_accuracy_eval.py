"""Inspect AI eval measuring the veyru stabilization judge against golden labels.

Each sample feeds the dataset's ``input`` (an observer action) and
``expected_input`` (the ground-truth procedure) to the REAL
``judge_stabilization`` LLM call, then scores the judge's ``match`` verdict
against the human-curated ``expected_match`` golden label. The headline metric
is accuracy; two extra metrics break accuracy down by whether the golden label
came from a unanimous or a split (2-1) majority vote during labeling.

Run it (the inspect ``--model`` is a placeholder — the judge call is made
inside the solver via the project's own LLM provider, not via inspect):

    VIRTUAL_ENV= uv run --no-sync inspect eval \
        src/glossogen/scenarios/veyru/evals/judge_accuracy_eval.py \
        --model mockllm/model

The judge model/provider default to the canonical judge
(``claude-haiku-4-5-20251001`` / ``anthropic``) and can be overridden with the
``VEYRU_JUDGE_MODEL`` / ``VEYRU_JUDGE_PROVIDER`` environment variables. Requires
``ANTHROPIC_API_KEY`` in the environment.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from inspect_ai import Task, task
from inspect_ai.dataset import Sample, csv_dataset
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Metric,
    SampleScore,
    Score,
    Target,
    accuracy,
    metric,
    scorer,
    stderr,
    value_to_float,
)
from inspect_ai.solver import Generate, TaskState, solver

from glossogen.llm.provider import LLMProvider
from glossogen.llm.provider_factory import create_provider
from glossogen.scenarios.veyru.stabilization_judge import judge_stabilization

load_dotenv()

DATASET_PATH = Path(__file__).parent / "veyru_judge_golden_labels.tsv"
DEFAULT_JUDGE_MODEL = os.environ.get("VEYRU_JUDGE_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_JUDGE_PROVIDER = os.environ.get("VEYRU_JUDGE_PROVIDER", "anthropic")


def record_to_sample(record: dict[str, str]) -> Sample:
    """Map one TSV row to an inspect Sample.

    ``input`` is the observer action under test; the golden ``expected_match``
    becomes the scoring target; the ground-truth procedure and labeling
    provenance ride along in metadata.
    """
    return Sample(
        input=record["input"],
        target=record["expected_match"].strip().upper(),
        metadata={
            "expected_input": record["expected_input"],
            "is_match": record["is_match"].strip().upper(),
            "split_vote": record["split_vote"].strip().upper(),
            "golden_explanation": record["explanation"],
        },
    )


@solver
def stabilization_judge_solver(judge_model: str, judge_provider: str):
    """Solver that runs the real stabilization judge on each sample.

    Bypasses inspect's model interface: it builds the project's own
    ``LLMProvider`` lazily on first use and calls ``judge_stabilization`` per
    sample, storing the boolean verdict and the judge's explanation on the task
    state. Lazy construction keeps ``ANTHROPIC_API_KEY`` out of the import path
    so the task and dataset can be inspected without credentials.
    """
    provider_cache: dict[str, LLMProvider] = {}

    def get_provider() -> LLMProvider:
        provider = provider_cache.get("provider")
        if provider is None:
            provider = create_provider(
                provider_name=judge_provider,
                model=judge_model,
                inference_provider=None,
                reasoning_effort=None,
            )
            provider_cache["provider"] = provider
        return provider

    async def solve(state: TaskState, generate: Generate) -> TaskState:  # noqa: ARG001
        judgment = await judge_stabilization(
            provider=get_provider(),
            expected_actions=state.metadata["expected_input"],
            observer_action=state.input_text,
        )
        verdict = "TRUE" if judgment.match else "FALSE"
        state.output.completion = verdict
        state.store.set("judge_match", judgment.match)
        state.store.set("judge_explanation", judgment.explanation)
        return state

    return solve


def _subset_accuracy(split_vote_value: str):
    """Build a metric computing accuracy over rows with the given split_vote flag."""
    to_float = value_to_float()

    def metric_fn(scores: list[SampleScore]) -> float:
        selected = [
            s for s in scores if (s.score.metadata or {}).get("split_vote") == split_vote_value
        ]
        if not selected:
            return 0.0
        return sum(to_float(s.score.value) for s in selected) / len(selected)

    return metric_fn


@metric
def accuracy_unanimous() -> Metric:
    """Accuracy over rows whose golden label was a unanimous (3-0) vote."""
    return _subset_accuracy("FALSE")


@metric
def accuracy_split() -> Metric:
    """Accuracy over rows whose golden label was a split (2-1) vote."""
    return _subset_accuracy("TRUE")


@scorer(metrics=[accuracy(), stderr(), accuracy_unanimous(), accuracy_split()])
def golden_match_scorer():
    """Score the judge's TRUE/FALSE verdict against the golden expected_match."""

    async def score(state: TaskState, target: Target) -> Score:
        judge_match = state.store.get("judge_match")
        verdict = "TRUE" if judge_match else "FALSE"
        gold = target.text.strip().upper()
        is_correct = verdict == gold
        return Score(
            value=CORRECT if is_correct else INCORRECT,
            answer=verdict,
            explanation=state.store.get("judge_explanation", ""),
            metadata={
                "judge_verdict": verdict,
                "golden": gold,
                "original_is_match": state.metadata["is_match"],
                "split_vote": state.metadata["split_vote"],
            },
        )

    return score


@task
def veyru_judge_accuracy(
    judge_model: str = DEFAULT_JUDGE_MODEL,
    judge_provider: str = DEFAULT_JUDGE_PROVIDER,
) -> Task:
    """Eval task: real stabilization judge vs golden labels over the full TSV."""
    return Task(
        dataset=csv_dataset(
            str(DATASET_PATH),
            record_to_sample,
            delimiter="\t",
        ),
        solver=stabilization_judge_solver(judge_model=judge_model, judge_provider=judge_provider),
        scorer=golden_match_scorer(),
    )
