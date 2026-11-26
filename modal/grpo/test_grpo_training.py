"""CPU tests of grpo_training.py on a tiny random model with Qwen3.8-27B's architecture.

The tiny model is built from Qwen3.8-27B's ``config.json``, made small, so the tests download that
one file from Hugging Face and no weights. They need torch, transformers and peft, which the
repository's environment does not install. Run them from the repository root in a throwaway one:

    uv run --no-project --python 3.12 --with torch==2.15.0 --with transformers==5.22.1 \\
      --with peft==0.21.2 --with safetensors==0.8.0 --with accelerate==1.15.0 --with pytest \\
      python -m pytest modal/grpo/test_grpo_training.py -p no:cacheprovider
"""

import json
import math
import tempfile
from pathlib import Path

import torch
from grpo_records import GrpoSettings, TrainingSequence
from grpo_training import (
    K3_MAX,
    capped_ratio,
    clamped_k3,
    load_state,
    marked_logprobs,
    new_optimizer,
    save_state,
    train_step,
    with_lora,
)
from huggingface_hub import hf_hub_download
from peft import PeftModel
from transformers import Qwen3_5Config, Qwen3_5ForConditionalGeneration

SEQUENCE_TOKENS = 120
MARKED = range(60, 100)
SETTINGS = GrpoSettings(
    lora_rank=8,
    lora_alpha=16,
    learning_rate=2e-2,
    kl_beta=0.05,
    max_grad_norm=1.0,
    logit_slice=16,
    ratio_cap=5.0,
)
CPU = torch.device("cpu")


def tiny_config() -> Qwen3_5Config:
    """Qwen3.8-27B's configuration with every size cut down, in float32."""
    config = json.loads(
        Path(hf_hub_download(repo_id="Qwen/Qwen3.8-27B", filename="config.json")).read_text()
    )
    text = config["text_config"]
    text.update(
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=4,
        layer_types=["linear_attention", "linear_attention", "linear_attention", "full_attention"],
        num_attention_heads=2,
        num_key_value_heads=1,
        head_dim=64,
        linear_num_key_heads=2,
        linear_num_value_heads=4,
        linear_key_head_dim=16,
        linear_value_head_dim=16,
        dtype="float32",
    )
    text["rope_parameters"]["mrope_section"] = [3, 3, 2]
    config["vision_config"].update(
        depth=1, hidden_size=32, num_heads=2, intermediate_size=64, out_hidden_size=64
    )
    return Qwen3_5Config(**config)


def fresh_model() -> PeftModel:
    """A tiny random model with a fresh adapter, the same one every time."""
    torch.manual_seed(0)
    return with_lora(model=Qwen3_5ForConditionalGeneration(tiny_config()), settings=SETTINGS)


def sequences(*, model: PeftModel, shift: float) -> list[TrainingSequence]:
    """Two sequences with tokens 60 to 99 marked: advantage +1 in the first, -1 in the second.

    Each marked token's sampler logprob is the model's own logprob minus ``shift``, so the
    importance ratio of every marked token starts at exp(shift).
    """
    generator = torch.Generator().manual_seed(1)
    built = []
    for advantage in (1.0, -1.0):
        input_ids = torch.randint(
            low=0,
            high=model.config.text_config.vocab_size,
            size=(SEQUENCE_TOKENS,),
            generator=generator,
        ).tolist()
        kl_mask = [int(position in MARKED) for position in range(SEQUENCE_TOKENS)]
        unsampled = TrainingSequence(
            input_ids=input_ids,
            kl_mask=kl_mask,
            advantages=[advantage * value for value in kl_mask],
            sampler_logprobs=[0.0] * SEQUENCE_TOKENS,
        )
        with torch.no_grad():
            own = marked_logprobs(
                model=model, sequence=unsampled, device=CPU, logit_slice=16, with_grad=False
            ).tolist()
        sampler = [0.0] * SEQUENCE_TOKENS
        for position, logprob in zip(MARKED, own, strict=True):
            sampler[position] = logprob - shift
        built.append(unsampled._replace(sampler_logprobs=sampler))
    return built


def mean_logprob(*, model: PeftModel, sequence: TrainingSequence) -> float:
    """The mean log-probability of the sequence's marked tokens."""
    with torch.no_grad():
        logprobs = marked_logprobs(
            model=model, sequence=sequence, device=CPU, logit_slice=16, with_grad=False
        )
    return float(logprobs.mean())


def test_k3_is_clamped_and_the_clamped_tokens_are_counted() -> None:
    result = clamped_k3(log_ratio=torch.tensor([0.0, 0.1, 13.5, -3.0]))
    assert result.clamped_tokens == 1
    assert float(result.k3[2]) == K3_MAX
    assert abs(float(result.k3[0])) < 1e-9
    assert float(result.k3[1]) < 0.01


def test_the_ratio_is_capped_without_a_gradient_and_its_statistics_are_counted() -> None:
    policy = torch.tensor([0.0, -1.0, 2.0], requires_grad=True)
    result = capped_ratio(policy=policy, sampler=torch.tensor([0.0, -1.5, -0.5]), cap=5.0)
    assert torch.allclose(result.weights, torch.tensor([1.0, math.exp(0.5), 5.0]))
    assert not result.weights.requires_grad
    assert abs(result.ratio_max - math.exp(2.5)) < 1e-4
    assert abs(result.ratio_sum - (1.0 + math.exp(0.5) + math.exp(2.5))) < 1e-4
    assert result.capped_tokens == 1


def test_a_token_whose_ratio_is_above_the_cap_weighs_the_cap() -> None:
    """At the first step the adapter is off, so k3 is 0 and the gradient is the policy term's."""
    unclipped = SETTINGS._replace(max_grad_norm=1e9)
    norms = []
    for shift in (0.0, 3.0):
        model = fresh_model()
        metrics = train_step(
            model=model,
            optimizer=new_optimizer(model=model, settings=unclipped),
            sequences=sequences(model=model, shift=shift),
            device=CPU,
            settings=unclipped,
        )
        norms.append(metrics.grad_norm)
        if shift:
            assert metrics.ratio_capped_share == 1.0
            assert abs(metrics.ratio_mean - math.exp(shift)) < 1e-3
    assert abs(norms[1] / norms[0] - unclipped.ratio_cap) < 1e-3


def test_lora_adapts_no_vision_module() -> None:
    model = fresh_model()
    adapted = [name for name, module in model.named_modules() if hasattr(module, "lora_A")]
    assert adapted
    assert not [name for name in adapted if "visual" in name]


def test_steps_move_log_probabilities_with_the_advantage_and_survive_a_reload() -> None:
    model = fresh_model()
    batch = sequences(model=model, shift=0.0)
    before = [mean_logprob(model=model, sequence=sequence) for sequence in batch]
    optimizer = new_optimizer(model=model, settings=SETTINGS)
    first = train_step(
        model=model, optimizer=optimizer, sequences=batch, device=CPU, settings=SETTINGS
    )
    assert abs(first.kl) < 1e-6
    assert abs(first.ratio_mean - 1.0) < 1e-4
    assert first.ratio_capped_share == 0.0
    metrics = first
    for _ in range(4):
        metrics = train_step(
            model=model, optimizer=optimizer, sequences=batch, device=CPU, settings=SETTINGS
        )
    assert metrics.kl > 0
    after = [mean_logprob(model=model, sequence=sequence) for sequence in batch]
    assert after[0] > before[0]
    assert after[1] < before[1]
    with tempfile.TemporaryDirectory() as directory:
        save_state(model=model, optimizer=optimizer, directory=Path(directory), metrics=metrics)
        restored = fresh_model()
        load_state(
            model=restored,
            optimizer=new_optimizer(model=restored, settings=SETTINGS),
            directory=Path(directory),
        )
        reloaded = [mean_logprob(model=restored, sequence=sequence) for sequence in batch]
    assert all(abs(a - b) < 1e-5 for a, b in zip(after, reloaded, strict=True))
