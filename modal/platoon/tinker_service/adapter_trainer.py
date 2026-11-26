"""The service's training backend: named adapters on one model, each with its own AdamW optimizer.

Each Tinker training client is one adapter, named by its model id, so that one service trains
several policies at once (platoon's ``policies:``). ``forward_backward`` computes each row's
logprobs and loss and adds the loss's gradient to the adapter's; ``optim_step`` clips the gradient
norm, steps the optimizer and clears the gradient. The model behind it is a ``LogprobModel``: a PEFT
model on a GPU (``peft_model``), or a unigram model on a CPU (``unigram_backend``).
"""

import math
from pathlib import Path
from typing import NamedTuple, Protocol

import torch
from tinker_service.losses import active_positions, row_loss
from tinker_service.records import AdamSettings, AdapterInfo, RowOutput, TrainingRow

ADAPTER_FOLDER = "adapter"
OPTIMIZER_FILE = "optimizer.pt"


class LogprobModel(Protocol):
    """What the trainer needs of a model with named adapters."""

    def add_adapter(self, *, name: str, rank: int, seed: int | None) -> list[torch.nn.Parameter]:
        """Add a fresh adapter that leaves the model's outputs unchanged, and return its
        parameters."""
        ...

    def target_logprobs(
        self, *, name: str, row: TrainingRow, active: torch.Tensor, with_grad: bool
    ) -> torch.Tensor:
        """The logprobs of the row's target tokens at its ``active`` positions, under adapter
        ``name``."""
        ...

    def save_adapter(self, *, name: str, directory: Path) -> None:
        """Write adapter ``name`` into ``directory`` in the format that the sampler loads."""
        ...

    def load_adapter(self, *, name: str, directory: Path) -> None:
        """Load into adapter ``name`` the weights that ``save_adapter`` wrote."""
        ...


class Adapter(NamedTuple):
    """One trained adapter: its rank, its parameters and its optimizer."""

    rank: int
    parameters: list[torch.nn.Parameter]
    optimizer: torch.optim.Optimizer


class AdapterTrainer:
    """Trains one adapter per model id on ``model``, a copy of ``base_model``."""

    def __init__(self, *, model: LogprobModel, base_model: str) -> None:
        self.model = model
        self.base_model = base_model
        self.adapters: dict[str, Adapter] = {}

    def adapter(self, *, model_id: str) -> Adapter:
        """The adapter of ``model_id``; refuse an unknown id."""
        if model_id not in self.adapters:
            raise ValueError(f"unknown model id {model_id!r}")
        return self.adapters[model_id]

    def create_adapter(self, *, model_id: str, rank: int, seed: int | None) -> None:
        """Add a fresh adapter of ``rank`` for ``model_id``, with a fresh optimizer."""
        if model_id in self.adapters:
            raise ValueError(f"model id {model_id!r} exists")
        parameters = self.model.add_adapter(name=model_id, rank=rank, seed=seed)
        optimizer = torch.optim.AdamW(params=parameters, weight_decay=0.0)
        self.adapters[model_id] = Adapter(rank=rank, parameters=parameters, optimizer=optimizer)

    def forward_backward(
        self,
        *,
        model_id: str,
        rows: list[TrainingRow],
        loss_fn: str,
        loss_fn_config: dict[str, float],
        backward: bool,
    ) -> list[RowOutput]:
        """Each row's logprobs and loss; with ``backward``, add each loss's gradient to the
        adapter's."""
        self.adapter(model_id=model_id)
        return [
            self.row_output(
                model_id=model_id,
                row=row,
                loss_fn=loss_fn,
                loss_fn_config=loss_fn_config,
                backward=backward,
            )
            for row in rows
        ]

    def row_output(
        self,
        *,
        model_id: str,
        row: TrainingRow,
        loss_fn: str,
        loss_fn_config: dict[str, float],
        backward: bool,
    ) -> RowOutput:
        """One row's logprobs, with 0 at the positions the loss does not read, and its loss."""
        active = active_positions(row=row)
        full = torch.zeros(len(row.target_tokens))
        if not bool(active.any()):
            return RowOutput(logprobs=full.tolist(), loss=0.0)
        logprobs = self.model.target_logprobs(
            name=model_id, row=row, active=active, with_grad=backward
        )
        loss = row_loss(loss_fn=loss_fn, config=loss_fn_config, logprobs=logprobs, row=row)
        if backward:
            loss.backward()
        full[active] = logprobs.detach().float().cpu()
        return RowOutput(logprobs=full.tolist(), loss=float(loss.detach()))

    def optim_step(self, *, model_id: str, adam: AdamSettings) -> dict[str, float]:
        """Clip the adapter's gradient norm, step its optimizer and clear its gradient."""
        adapter = self.adapter(model_id=model_id)
        for group in adapter.optimizer.param_groups:
            group["lr"] = adam.learning_rate
            group["betas"] = (adam.beta1, adam.beta2)
            group["eps"] = adam.eps
            group["weight_decay"] = adam.weight_decay
        max_norm = math.inf
        if adam.grad_clip_norm > 0:
            max_norm = adam.grad_clip_norm
        grad_norm = torch.nn.utils.clip_grad_norm_(parameters=adapter.parameters, max_norm=max_norm)
        adapter.optimizer.step()
        adapter.optimizer.zero_grad(set_to_none=True)
        return {"grad_norm": float(grad_norm)}

    def info(self, *, model_id: str) -> AdapterInfo:
        """The base model and rank of ``model_id``'s adapter."""
        return AdapterInfo(base_model=self.base_model, rank=self.adapter(model_id=model_id).rank)

    def save_state(self, *, model_id: str, directory: Path) -> None:
        """Write the adapter and its optimizer state into ``directory``."""
        adapter = self.adapter(model_id=model_id)
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save_adapter(name=model_id, directory=directory / ADAPTER_FOLDER)
        torch.save(adapter.optimizer.state_dict(), directory / OPTIMIZER_FILE)

    def load_state(self, *, model_id: str, directory: Path, with_optimizer: bool) -> None:
        """Load the adapter, and with ``with_optimizer`` its optimizer state, that ``save_state``
        wrote."""
        adapter = self.adapter(model_id=model_id)
        self.model.load_adapter(name=model_id, directory=directory / ADAPTER_FOLDER)
        if with_optimizer:
            state = torch.load(directory / OPTIMIZER_FILE, weights_only=True)
            adapter.optimizer.load_state_dict(state)

    def save_sampler_weights(self, *, model_id: str, directory: Path) -> None:
        """Write the adapter into ``directory`` in the format that the sampler loads."""
        self.adapter(model_id=model_id)
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save_adapter(name=model_id, directory=directory)
