"""The Tinker-API service, driven over HTTP by the Tinker SDK that platoon uses (tinker 0.16.1),
with CPU backends: the scripted sampler and the unigram trainer."""

import math
from collections.abc import Iterator
from pathlib import Path

import aiohttp
import pytest
import tinker
import torch
from service_thread import API_KEY, PROMPT_LOGPROB, SAMPLED_LOGPROB, RunningService, running_service
from tinker import types
from tinker_service.scripted_backend import SampleCall

BASE_MODEL = "glossogen/toy-base"
RANK = 4
COMPLETION = "a scripted reply"


def scripted_reply(prompt: str) -> str:
    """The same completion for every prompt."""
    del prompt
    return COMPLETION


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RunningService]:
    """The CPU service, with the SDK's environment pointing at it."""
    with running_service(base_model=BASE_MODEL, script=scripted_reply, root=tmp_path) as running:
        monkeypatch.setenv("TINKER_API_KEY", API_KEY)
        monkeypatch.setenv("TINKER_BASE_URL", running.url)
        monkeypatch.setenv("TINKER_TELEMETRY", "0")
        yield running


def rl_datum(*, tokens: list[int], advantage: float) -> types.Datum:
    """A datum whose last three target tokens are actions, sampled at SAMPLED_LOGPROB, with
    ``advantage``."""
    targets = [*tokens[1:], tokens[0]]
    actions = [0.0] * (len(tokens) - 3) + [1.0] * 3
    return types.Datum(
        model_input=types.ModelInput.from_ints(tokens),
        loss_fn_inputs={
            "target_tokens": types.TensorData(data=targets, dtype="int64", shape=[len(targets)]),
            "logprobs": types.TensorData(
                data=[SAMPLED_LOGPROB * action for action in actions],
                dtype="float32",
                shape=[len(actions)],
            ),
            "advantages": types.TensorData(
                data=[advantage * action for action in actions],
                dtype="float32",
                shape=[len(actions)],
            ),
        },
    )


def test_a_cispo_step_computes_logprobs_and_loss_and_moves_the_adapter(
    served: RunningService,
) -> None:
    client = tinker.ServiceClient().create_lora_training_client(base_model=BASE_MODEL, rank=RANK)
    datum = rl_datum(tokens=[72, 105, 33, 10, 72, 105], advantage=1.0)
    config = {"clip_low_threshold": 0.0, "clip_high_threshold": 5.0}
    result = client.forward_backward([datum], loss_fn="cispo", loss_fn_config=config).result()
    uniform = -math.log(served.model.vocab_size)
    logprobs = result.loss_fn_outputs[0]["logprobs"].to_torch()
    assert logprobs[:-3].tolist() == [0.0] * 3
    assert logprobs[-3:].tolist() == pytest.approx([uniform] * 3, abs=1e-5)
    ratio = math.exp(uniform - SAMPLED_LOGPROB)
    assert result.metrics["loss:sum"] == pytest.approx(-3 * ratio * uniform, rel=1e-4)
    step = client.optim_step(types.AdamParams(learning_rate=0.1, grad_clip_norm=1.0)).result()
    assert step.metrics is not None and step.metrics["grad_norm"] > 0
    after = client.forward_backward([datum], loss_fn="cispo", loss_fn_config=config).result()
    assert after.loss_fn_outputs[0]["logprobs"].to_torch()[-1] > uniform


def test_a_published_sampler_samples_the_script_and_the_base_model_scores_prompts(
    served: RunningService,
) -> None:
    service_client = tinker.ServiceClient()
    client = service_client.create_lora_training_client(base_model=BASE_MODEL, rank=RANK)
    sampler = client.save_weights_and_get_sampling_client()
    prompt = types.ModelInput.from_ints([72, 105, 10])
    params = types.SamplingParams(max_tokens=64, temperature=1.0)
    sampled = sampler.sample(prompt=prompt, num_samples=1, sampling_params=params).result()
    tokens = sampled.sequences[0].tokens
    assert bytes(tokens[:-1]).decode() == COMPLETION
    assert sampled.sequences[0].stop_reason == "stop"
    assert sampled.sequences[0].logprobs == [SAMPLED_LOGPROB] * len(tokens)
    assert served.sampler.calls[-1].adapter is not None
    base = service_client.create_sampling_client(base_model=BASE_MODEL)
    scored = base.compute_logprobs(prompt).result()
    assert scored == [None, PROMPT_LOGPROB, PROMPT_LOGPROB]
    assert served.sampler.calls[-1] == SampleCall(adapter=None, scoring=True)


@pytest.mark.usefixtures("served")
def test_a_full_checkpoint_resumes_into_a_new_client() -> None:
    service_client = tinker.ServiceClient()
    client = service_client.create_lora_training_client(base_model=BASE_MODEL, rank=RANK)
    datum = rl_datum(tokens=[65, 66, 67, 68], advantage=2.0)
    client.forward_backward([datum], loss_fn="importance_sampling").result()
    client.optim_step(types.AdamParams(learning_rate=0.05)).result()
    path = client.save_state("after-one-step").result().path
    assert path.startswith("tinker://") and path.endswith("/weights/after-one-step")
    trained = client.forward_backward([datum], loss_fn="importance_sampling").result()
    resumed = service_client.create_training_client_from_state_with_optimizer(path)
    again = resumed.forward_backward([datum], loss_fn="importance_sampling").result()
    assert torch.allclose(
        again.loss_fn_outputs[0]["logprobs"].to_torch(),
        trained.loss_fn_outputs[0]["logprobs"].to_torch(),
    )
    info = service_client.create_rest_client().get_weights_info_by_tinker_path(path).result()
    assert (info.base_model, info.is_lora, info.lora_rank) == (BASE_MODEL, True, RANK)


async def test_a_request_without_the_api_key_is_refused(served: RunningService) -> None:
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{served.url}/api/v1/create_session", json={}) as reply:
            assert reply.status == 401
        headers = {"X-API-Key": API_KEY}
        body = {"session_id": "s", "model_seq_id": 0, "base_model": "another/model"}
        async with http.post(
            f"{served.url}/api/v1/create_model", json=body, headers=headers
        ) as reply:
            assert reply.status == 400
