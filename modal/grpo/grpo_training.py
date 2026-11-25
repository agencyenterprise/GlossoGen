"""One on-policy GRPO step with LoRA on Qwen3.8-27B, and the adapter's saved state.

A training sequence holds a player's prompts and answers as the model received and wrote them.
``kl_mask`` marks the answer tokens, and ``advantages`` gives each of them its round's advantage.
The loss over a batch is

    sum over marked tokens of ( -advantage * log p_policy(token) + kl_beta * k3 ) / marked tokens,

with k3 = exp(r) - r - 1 and r = log p_reference - log p_policy. The reference is the same model
with the adapter switched off. k3 is clamped at K3_MAX per token, as the verl library does, and
the step's metrics count the clamped tokens. Each batch is used for one optimizer step. The policy
that played the games is therefore the one being updated, and the loss needs no probability
ratio.

Only marked positions go through the LM head, in slices of ``logit_slice`` positions. LoRA adapts
the language model's modules whose names are in LORA_TARGET_MODULES. The adapter lists them by
full name, which keeps the vision modules out of it. The linear-attention projections have other
names, so they are left out too. In transformers,
Qwen3.8-27B is a ``Qwen3_5ForConditionalGeneration``. Used by grpo_app.py on Modal and by
test_grpo_training.py on CPU.
"""

import json
import time
from pathlib import Path
from typing import NamedTuple

import torch
import torch.nn.functional as functional
from grpo_records import GrpoSettings, StepMetrics, TrainingSequence
from peft import LoraConfig, PeftModel, get_peft_model, set_peft_model_state_dict
from safetensors.torch import load_file
from torch.utils.checkpoint import checkpoint

LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
LANGUAGE_MODEL_PREFIX = "model.language_model."
K3_MAX = 10.0


class ClampedK3(NamedTuple):
    """The per-token KL estimate after clamping, and how many tokens were above the clamp."""

    k3: torch.Tensor
    clamped_tokens: int


def language_model_targets(*, model: torch.nn.Module) -> list[str]:
    """The full names of the language-model modules that LoRA adapts.

    Naming them one by one keeps every vision module out of the adapter.
    """
    return [
        name
        for name, _ in model.named_modules()
        if name.startswith(LANGUAGE_MODEL_PREFIX) and name.rsplit(".", 1)[-1] in LORA_TARGET_MODULES
    ]


def with_lora(*, model: torch.nn.Module, settings: GrpoSettings) -> PeftModel:
    """Wrap ``model`` in a LoRA adapter.

    The adapter's B matrices start at 0, so the adapted model first plays as the base model.
    """
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    config = LoraConfig(
        r=settings.lora_rank,
        lora_alpha=settings.lora_alpha,
        lora_dropout=0.0,
        bias="none",
        target_modules=language_model_targets(model=model),
    )
    peft_model = get_peft_model(model=model, peft_config=config)
    peft_model.print_trainable_parameters()
    return peft_model


def sliced_logprobs(
    hidden: torch.Tensor, labels: torch.Tensor, lm_head: torch.nn.Module
) -> torch.Tensor:
    """Log-probabilities of ``labels`` for one slice of positions.

    Its arguments are positional because ``torch.utils.checkpoint`` passes them that way.
    """
    logits = lm_head(hidden).float()
    return (
        functional.log_softmax(logits, dim=-1)
        .gather(dim=-1, index=labels.unsqueeze(-1))
        .squeeze(-1)
    )


def marked_logprobs(
    *,
    model: PeftModel,
    sequence: TrainingSequence,
    device: torch.device,
    logit_slice: int,
    with_grad: bool,
) -> torch.Tensor:
    """The log-probability of every marked token, in order. Position t predicts token t+1."""
    base = model.base_model.model
    input_ids = torch.tensor([sequence.input_ids], device=device)
    hidden = base.model(input_ids=input_ids, use_cache=False).last_hidden_state[0, :-1]
    marked = torch.tensor(sequence.kl_mask[1:], device=device, dtype=torch.bool)
    selected = hidden[marked]
    labels = input_ids[0, 1:][marked]
    pieces: list[torch.Tensor] = []
    for start in range(0, selected.shape[0], logit_slice):
        hidden_slice = selected[start : start + logit_slice]
        label_slice = labels[start : start + logit_slice]
        if with_grad:
            piece = checkpoint(
                sliced_logprobs, hidden_slice, label_slice, base.lm_head, use_reentrant=False
            )
        else:
            piece = sliced_logprobs(hidden_slice, label_slice, base.lm_head)
        pieces.append(piece)
    return torch.cat(pieces)


def reference_logprobs(
    *, model: PeftModel, sequence: TrainingSequence, device: torch.device, logit_slice: int
) -> torch.Tensor:
    """The log-probability of every marked token with the adapter switched off."""
    with torch.no_grad(), model.disable_adapter():
        return marked_logprobs(
            model=model, sequence=sequence, device=device, logit_slice=logit_slice, with_grad=False
        )


def clamped_k3(*, log_ratio: torch.Tensor) -> ClampedK3:
    """k3 = exp(r) - r - 1 per token, clamped at K3_MAX, and the number of tokens above it."""
    unclamped = torch.exp(log_ratio) - log_ratio - 1.0
    return ClampedK3(
        k3=torch.clamp(unclamped, max=K3_MAX), clamped_tokens=int((unclamped > K3_MAX).sum())
    )


def peak_memory_gb(*, device: torch.device) -> float:
    """The most GPU memory allocated since ``train_step`` reset the count, in GB.

    On a CPU it returns 0.
    """
    if device.type != "cuda":
        return 0.0
    return torch.cuda.max_memory_allocated(device=device) / 1e9


def train_step(
    *,
    model: PeftModel,
    optimizer: torch.optim.Optimizer,
    sequences: list[TrainingSequence],
    device: torch.device,
    settings: GrpoSettings,
) -> StepMetrics:
    """Accumulate the batch's gradient sequence by sequence, then take one optimizer step."""
    began = time.monotonic()
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device=device)
    marked_tokens = sum(sum(sequence.kl_mask[1:]) for sequence in sequences)
    if marked_tokens == 0:
        raise ValueError("the batch has no marked tokens")
    policy_total = 0.0
    kl_total = 0.0
    clamped_tokens = 0
    model.train()
    for sequence in sequences:
        if sum(sequence.kl_mask[1:]) == 0:
            continue
        reference = reference_logprobs(
            model=model, sequence=sequence, device=device, logit_slice=settings.logit_slice
        )
        policy = marked_logprobs(
            model=model,
            sequence=sequence,
            device=device,
            logit_slice=settings.logit_slice,
            with_grad=True,
        )
        marked = [index for index, value in enumerate(sequence.kl_mask[1:], start=1) if value]
        advantages = torch.tensor([sequence.advantages[index] for index in marked], device=device)
        clamped = clamped_k3(log_ratio=reference - policy)
        clamped_tokens += clamped.clamped_tokens
        policy_sum = -(advantages * policy).sum()
        kl_sum = clamped.k3.sum()
        ((policy_sum + settings.kl_beta * kl_sum) / marked_tokens).backward()
        policy_total += float(policy_sum.detach())
        kl_total += float(kl_sum.detach())
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    grad_norm = torch.nn.utils.clip_grad_norm_(
        parameters=parameters, max_norm=settings.max_grad_norm
    )
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    return StepMetrics(
        policy_loss=policy_total / marked_tokens,
        kl=kl_total / marked_tokens,
        marked_tokens=marked_tokens,
        advantaged_tokens=sum(
            1
            for sequence in sequences
            for index, value in enumerate(sequence.kl_mask)
            if value and sequence.advantages[index]
        ),
        tokens=sum(len(sequence.input_ids) for sequence in sequences),
        grad_norm=float(grad_norm),
        clamped_tokens=clamped_tokens,
        seconds=time.monotonic() - began,
        peak_memory_gb=peak_memory_gb(device=device),
    )


def new_optimizer(*, model: PeftModel, settings: GrpoSettings) -> torch.optim.Optimizer:
    """AdamW over the adapter's parameters, with no weight decay."""
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    return torch.optim.AdamW(params=parameters, lr=settings.learning_rate, weight_decay=0.0)


def save_state(
    *,
    model: PeftModel,
    optimizer: torch.optim.Optimizer,
    directory: Path,
    metrics: StepMetrics | None,
) -> None:
    """Save the adapter as vLLM loads it, and the optimizer state.

    The step's metrics are saved too, when there are any.
    """
    directory.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(save_directory=str(directory))
    torch.save(optimizer.state_dict(), directory / "optimizer.pt")
    if metrics is not None:
        (directory / "metrics.json").write_text(json.dumps(metrics._asdict(), indent=1) + "\n")


def load_state(*, model: PeftModel, optimizer: torch.optim.Optimizer, directory: Path) -> None:
    """Restore the adapter weights and the optimizer state that ``save_state`` saved."""
    weights = load_file(filename=str(directory / "adapter_model.safetensors"))
    result = set_peft_model_state_dict(model=model, peft_model_state_dict=weights)
    if result.unexpected_keys:
        raise ValueError(
            f"{len(result.unexpected_keys)} unexpected adapter keys, "
            f"first: {result.unexpected_keys[:3]}"
        )
    optimizer.load_state_dict(torch.load(directory / "optimizer.pt", weights_only=True))
