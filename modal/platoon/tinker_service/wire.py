"""Decoding the Tinker SDK's request types into the service's records, and encoding results into its
response types.

The service parses each request body with the SDK's own pydantic types (``tinker.types``), so a body
the SDK would not send is refused the way the SDK's types refuse it.
"""

from typing import NamedTuple

from tinker import types
from tinker_service.records import (
    AdamSettings,
    RowOutput,
    SampledSequence,
    SampleResult,
    SamplingRequest,
    TrainingRow,
)

LOSS_KEY = "loss:sum"


class StopLists(NamedTuple):
    """A ``stop`` of the Tinker API, split into its strings and its token ids."""

    strings: list[str]
    tokens: list[int]


def float_values(*, datum: types.Datum, key: str) -> list[float] | None:
    """The datum's ``loss_fn_inputs[key]`` as floats, or None when it has none."""
    if key not in datum.loss_fn_inputs:
        return None
    return [float(value) for value in datum.loss_fn_inputs[key].data]


def training_row(*, datum: types.Datum) -> TrainingRow:
    """One datum as a row; refuse targets that are not the input shifted by one, plus one token."""
    input_tokens = list(datum.model_input.to_ints())
    target_tokens = [int(token) for token in datum.loss_fn_inputs["target_tokens"].data]
    if len(target_tokens) != len(input_tokens) or target_tokens[:-1] != input_tokens[1:]:
        raise ValueError("target_tokens must be the model input shifted by one token")
    return TrainingRow(
        input_tokens=input_tokens,
        target_tokens=target_tokens,
        sampling_logprobs=float_values(datum=datum, key="logprobs"),
        advantages=float_values(datum=datum, key="advantages"),
        weights=float_values(datum=datum, key="weights"),
    )


def adam_settings(*, params: types.AdamParams) -> AdamSettings:
    """The optimizer settings of an ``optim_step`` request."""
    return AdamSettings(
        learning_rate=params.learning_rate,
        beta1=params.beta1,
        beta2=params.beta2,
        eps=params.eps,
        weight_decay=params.weight_decay,
        grad_clip_norm=params.grad_clip_norm,
    )


def stop_lists(*, stop: str | list[str] | list[int] | None) -> StopLists:
    """A ``stop`` of the Tinker API as its strings and its token ids."""
    if stop is None:
        return StopLists(strings=[], tokens=[])
    if isinstance(stop, str):
        return StopLists(strings=[stop], tokens=[])
    return StopLists(
        strings=[value for value in stop if isinstance(value, str)],
        tokens=[int(value) for value in stop if isinstance(value, int)],
    )


def sampling_request(*, request: types.SampleRequest) -> SamplingRequest:
    """The prompt and the sampling settings of an ``asample`` request."""
    params = request.sampling_params
    stop = stop_lists(stop=params.stop)  # type: ignore[arg-type]
    return SamplingRequest(
        prompt=list(request.prompt.to_ints()),
        max_tokens=params.max_tokens,
        temperature=params.temperature,
        top_k=params.top_k,
        top_p=params.top_p,
        seed=params.seed,
        stop_strings=stop.strings,
        stop_tokens=stop.tokens,
        num_samples=request.num_samples,
        prompt_logprobs=bool(request.prompt_logprobs),
    )


def float_tensor(*, values: list[float]) -> types.TensorData:
    """A one-dimensional float tensor."""
    return types.TensorData(data=values, dtype="float32", shape=[len(values)])


def forward_backward_output(*, outputs: list[RowOutput]) -> types.ForwardBackwardOutput:
    """The response of ``forward_backward``: each row's logprobs and loss, and the total loss.

    The SDK combines the metrics of a request's chunks by the reduction after the colon of each
    name.
    """
    return types.ForwardBackwardOutput(
        loss_fn_output_type="ArrayRecord",
        loss_fn_outputs=[
            {
                "logprobs": float_tensor(values=output.logprobs),
                LOSS_KEY: float_tensor(values=[output.loss]),
            }
            for output in outputs
        ],
        metrics={LOSS_KEY: sum(output.loss for output in outputs)},
    )


def sampled_sequence(*, sequence: SampledSequence) -> types.SampledSequence:
    """One sampled sequence in the response's type."""
    return types.SampledSequence(
        stop_reason=sequence.stop_reason,  # type: ignore[arg-type]
        tokens=sequence.tokens,
        logprobs=sequence.logprobs,
    )


def sample_response(*, result: SampleResult) -> types.SampleResponse:
    """The response of ``asample``."""
    return types.SampleResponse(
        sequences=[sampled_sequence(sequence=sequence) for sequence in result.sequences],
        prompt_logprobs=result.prompt_logprobs,
    )
