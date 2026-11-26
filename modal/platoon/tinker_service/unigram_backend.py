"""A ``LogprobModel`` for CPU tests: each adapter is one vector of logits over the vocabulary.

A token's logprob ignores its context: it is the token's entry of the log-softmax of the adapter's
logits. A fresh adapter's logits are 0, so every token starts with the same logprob. The model has
real parameters, gradients and optimizer steps, and costs one vector per adapter, so a test can
train on games of any length.
"""

from pathlib import Path

import torch
from tinker_service.records import TrainingRow

WEIGHTS_FILE = "unigram.pt"


class UnigramModel:
    """Unigram logits per adapter, over a vocabulary of ``vocab_size`` tokens."""

    def __init__(self, *, vocab_size: int) -> None:
        self.vocab_size = vocab_size
        self.logits: dict[str, torch.nn.Parameter] = {}

    def add_adapter(self, *, name: str, rank: int, seed: int | None) -> list[torch.nn.Parameter]:
        """A fresh adapter of zero logits; the rank and the seed do not change it."""
        del rank, seed
        self.logits[name] = torch.nn.Parameter(torch.zeros(self.vocab_size))
        return [self.logits[name]]

    def target_logprobs(
        self, *, name: str, row: TrainingRow, active: torch.Tensor, with_grad: bool
    ) -> torch.Tensor:
        """The unigram logprob of each active target token."""
        targets = torch.tensor(row.target_tokens)[active]
        with torch.set_grad_enabled(with_grad):
            return torch.log_softmax(self.logits[name], dim=0)[targets]

    def save_adapter(self, *, name: str, directory: Path) -> None:
        """Write the adapter's logits."""
        directory.mkdir(parents=True, exist_ok=True)
        torch.save({"logits": self.logits[name].detach()}, directory / WEIGHTS_FILE)

    def load_adapter(self, *, name: str, directory: Path) -> None:
        """Load the logits that ``save_adapter`` wrote."""
        saved = torch.load(directory / WEIGHTS_FILE, weights_only=True)
        with torch.no_grad():
            self.logits[name].copy_(saved["logits"])
