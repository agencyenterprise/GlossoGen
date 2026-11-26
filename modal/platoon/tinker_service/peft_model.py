"""A ``LogprobModel`` over a Hugging Face causal language model with one PEFT LoRA adapter per
trained policy.

Each adapter adapts the modules under ``module_prefix`` whose last name is in
``LORA_TARGET_MODULES``, listed by full name. In transformers, Qwen3.8-27B is a
``Qwen3_5ForConditionalGeneration``, whose language model's modules are under
``model.language_model.``: naming them one by one keeps the vision modules out of the adapter, and
the linear-attention projections, which have other names, are left out too. The LoRA alpha is twice
the rank. A fresh adapter's B matrices are 0, so it leaves the model's outputs unchanged.

Only the positions that the loss reads go through the LM head, in slices of ``logit_slice``
positions, each slice recomputed in the backward pass, so a long game fits in memory. The model
trains with gradient checkpointing. An adapter is saved as ``adapter_config.json`` and
``adapter_model.safetensors``, the files vLLM loads.
"""

from pathlib import Path
from typing import NamedTuple

import torch
import torch.nn.functional as functional
from peft import (
    LoraConfig,
    PeftModel,
    get_peft_model,
    get_peft_model_state_dict,
    set_peft_model_state_dict,
)
from safetensors.torch import load_file, save_file
from tinker_service.records import TrainingRow
from torch.utils.checkpoint import checkpoint

LORA_TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
LORA_ALPHA_PER_RANK = 2
WEIGHTS_FILE = "adapter_model.safetensors"


class PeftSettings(NamedTuple):
    """Which modules the adapters adapt, and how many positions go through the LM head at once."""

    module_prefix: str
    logit_slice: int


def adapted_modules(*, model: torch.nn.Module, module_prefix: str) -> list[str]:
    """The full names of the modules that LoRA adapts."""
    return [
        name
        for name, _ in model.named_modules()
        if name.startswith(module_prefix) and name.rsplit(".", 1)[-1] in LORA_TARGET_MODULES
    ]


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


class PeftLogprobModel:
    """``model`` with one LoRA adapter per name, on the device that holds its parameters."""

    def __init__(self, *, model: torch.nn.Module, settings: PeftSettings) -> None:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.config.use_cache = False
        self.model = model
        self.settings = settings
        self.device = next(model.parameters()).device
        self.peft: PeftModel | None = None
        self.parameters: dict[str, list[torch.nn.Parameter]] = {}

    def wrapped(self) -> PeftModel:
        """The PEFT model; refuse a call before the first adapter exists."""
        if self.peft is None:
            raise ValueError("no adapter exists yet")
        return self.peft

    def add_adapter(self, *, name: str, rank: int, seed: int | None) -> list[torch.nn.Parameter]:
        """Add a fresh adapter of ``rank`` named ``name``, and return its parameters."""
        if seed is not None:
            torch.manual_seed(seed)
        config = LoraConfig(
            r=rank,
            lora_alpha=LORA_ALPHA_PER_RANK * rank,
            lora_dropout=0.0,
            bias="none",
            target_modules=adapted_modules(
                model=self.model, module_prefix=self.settings.module_prefix
            ),
        )
        if self.peft is None:
            self.peft = get_peft_model(model=self.model, peft_config=config, adapter_name=name)
        else:
            self.peft.add_adapter(adapter_name=name, peft_config=config)
        marker = f".{name}."
        parameters = [
            parameter
            for full_name, parameter in self.wrapped().named_parameters()
            if marker in full_name
        ]
        self.parameters[name] = parameters
        return parameters

    def activate(self, *, name: str) -> PeftModel:
        """Make ``name`` the adapter that the forward pass applies, with its parameters
        trainable."""
        peft = self.wrapped()
        peft.set_adapter(name)
        for parameter in self.parameters[name]:
            parameter.requires_grad_(True)
        return peft

    def target_logprobs(
        self, *, name: str, row: TrainingRow, active: torch.Tensor, with_grad: bool
    ) -> torch.Tensor:
        """The logprobs of the row's target tokens at its ``active`` positions, under adapter
        ``name``."""
        peft = self.activate(name=name)
        causal_lm = peft.base_model.model
        peft.train()
        input_ids = torch.tensor([row.input_tokens], device=self.device)
        selected = active.to(self.device)
        labels = torch.tensor(row.target_tokens, device=self.device)[selected]
        with torch.set_grad_enabled(with_grad):
            hidden = causal_lm.model(input_ids=input_ids, use_cache=False).last_hidden_state[0]
            return self.head_logprobs(
                hidden=hidden[selected],
                labels=labels,
                lm_head=causal_lm.lm_head,
                with_grad=with_grad,
            )

    def head_logprobs(
        self,
        *,
        hidden: torch.Tensor,
        labels: torch.Tensor,
        lm_head: torch.nn.Module,
        with_grad: bool,
    ) -> torch.Tensor:
        """The LM head's logprobs of ``labels``, ``logit_slice`` positions at a time."""
        pieces: list[torch.Tensor] = []
        for start in range(0, hidden.shape[0], self.settings.logit_slice):
            hidden_slice = hidden[start : start + self.settings.logit_slice]
            label_slice = labels[start : start + self.settings.logit_slice]
            if with_grad:
                piece = checkpoint(
                    sliced_logprobs, hidden_slice, label_slice, lm_head, use_reentrant=False
                )
            else:
                piece = sliced_logprobs(hidden_slice, label_slice, lm_head)
            pieces.append(piece)
        return torch.cat(pieces)

    def save_adapter(self, *, name: str, directory: Path) -> None:
        """Write adapter ``name``'s config and weights, without the adapter's name in the weights'
        keys."""
        peft = self.wrapped()
        directory.mkdir(parents=True, exist_ok=True)
        weights = get_peft_model_state_dict(peft, adapter_name=name)
        save_file(
            {key: value.contiguous() for key, value in weights.items()}, directory / WEIGHTS_FILE
        )
        peft.peft_config[name].save_pretrained(str(directory))

    def load_adapter(self, *, name: str, directory: Path) -> None:
        """Load into adapter ``name`` the weights that ``save_adapter`` wrote; refuse unexpected
        keys."""
        weights = load_file(filename=str(directory / WEIGHTS_FILE), device=str(self.device))
        result = set_peft_model_state_dict(self.wrapped(), weights, adapter_name=name)
        if result.unexpected_keys:
            raise ValueError(
                f"{len(result.unexpected_keys)} unexpected adapter keys, "
                f"first: {result.unexpected_keys[:3]}"
            )
