"""The GPU trainer's model on CPU: the trainer over PEFT adapters on a tiny random model of
Qwen3.8-27B's architecture (``Qwen3_5ForConditionalGeneration``, built here with every size cut
down, with no download).
"""

import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import load_file
from tinker_service.adapter_trainer import AdapterTrainer
from tinker_service.losses import active_positions
from tinker_service.peft_model import WEIGHTS_FILE, PeftLogprobModel, PeftSettings
from tinker_service.records import AdamSettings, TrainingRow
from transformers import Qwen3_5Config, Qwen3_5ForConditionalGeneration

VOCAB = 300
RANK = 4
SETTINGS = PeftSettings(module_prefix="model.language_model.", logit_slice=3)
ADAM = AdamSettings(
    learning_rate=5e-2, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.0, grad_clip_norm=1.0
)
CISPO = {"clip_low_threshold": 0.0, "clip_high_threshold": 5.0}
BASE_MODEL = "tiny/qwen3.8-architecture"


def tiny_model() -> Qwen3_5ForConditionalGeneration:
    """A random model of Qwen3.8-27B's architecture with every size cut down, the same one every
    time."""
    text = {
        "vocab_size": VOCAB,
        "hidden_size": 64,
        "intermediate_size": 128,
        "num_hidden_layers": 4,
        "layer_types": ["linear_attention"] * 3 + ["full_attention"],
        "num_attention_heads": 2,
        "num_key_value_heads": 1,
        "head_dim": 64,
        "linear_num_key_heads": 2,
        "linear_num_value_heads": 4,
        "linear_key_head_dim": 16,
        "linear_value_head_dim": 16,
        "dtype": "float32",
        "rope_parameters": {
            "rope_theta": 10000.0,
            "partial_rotary_factor": 0.25,
            "rope_type": "default",
            "mrope_section": [3, 3, 2],
        },
    }
    vision = {
        "depth": 1,
        "hidden_size": 32,
        "num_heads": 2,
        "intermediate_size": 64,
        "out_hidden_size": 64,
    }
    torch.manual_seed(0)
    return Qwen3_5ForConditionalGeneration(Qwen3_5Config(text_config=text, vision_config=vision))


def rl_row(*, advantage: float) -> TrainingRow:
    """A row of 12 tokens whose last five target tokens are actions with ``advantage``."""
    tokens = [(7 * index + 3) % VOCAB for index in range(13)]
    actions = [0.0] * 7 + [1.0] * 5
    return TrainingRow(
        input_tokens=tokens[:-1],
        target_tokens=tokens[1:],
        sampling_logprobs=[-5.7 * action for action in actions],
        advantages=[advantage * action for action in actions],
        weights=None,
    )


def trainer() -> AdapterTrainer:
    """A trainer over the tiny model."""
    model = PeftLogprobModel(model=tiny_model(), settings=SETTINGS)
    return AdapterTrainer(model=model, base_model=BASE_MODEL)


def logprobs(*, trained: AdapterTrainer, model_id: str, row: TrainingRow) -> torch.Tensor:
    """The adapter's logprobs of the row's active target tokens."""
    active = active_positions(row=row)
    return trained.model.target_logprobs(name=model_id, row=row, active=active, with_grad=False)


def test_a_fresh_adapter_leaves_the_model_unchanged() -> None:
    trained = trainer()
    row = rl_row(advantage=1.0)
    trained.create_adapter(model_id="a", rank=RANK, seed=1)
    base = tiny_model()
    with torch.no_grad():
        hidden = base.model(input_ids=torch.tensor([row.input_tokens])).last_hidden_state[0]
        expected = torch.log_softmax(base.lm_head(hidden), dim=-1)
    targets = torch.tensor(row.target_tokens)
    active = active_positions(row=row)
    expected_active = expected[torch.arange(len(targets)), targets][active]
    assert torch.allclose(
        logprobs(trained=trained, model_id="a", row=row), expected_active, atol=1e-5
    )


def test_a_cispo_step_raises_the_advantaged_tokens_of_its_own_adapter_only() -> None:
    trained = trainer()
    row = rl_row(advantage=1.0)
    trained.create_adapter(model_id="a", rank=RANK, seed=1)
    trained.create_adapter(model_id="b", rank=RANK, seed=2)
    before_a = logprobs(trained=trained, model_id="a", row=row)
    before_b = logprobs(trained=trained, model_id="b", row=row)
    for _ in range(3):
        outputs = trained.forward_backward(
            model_id="a", rows=[row], loss_fn="cispo", loss_fn_config=CISPO, backward=True
        )
        metrics = trained.optim_step(model_id="a", adam=ADAM)
    assert metrics["grad_norm"] > 0
    assert outputs[0].logprobs[:7] == [0.0] * 7
    assert logprobs(trained=trained, model_id="a", row=row).sum() > before_a.sum()
    assert torch.equal(logprobs(trained=trained, model_id="b", row=row), before_b)


def test_a_saved_state_loads_into_a_new_adapter(tmp_path: Path) -> None:
    trained = trainer()
    row = rl_row(advantage=-1.0)
    trained.create_adapter(model_id="a", rank=RANK, seed=1)
    trained.forward_backward(
        model_id="a", rows=[row], loss_fn="cispo", loss_fn_config=CISPO, backward=True
    )
    trained.optim_step(model_id="a", adam=ADAM)
    trained.save_state(model_id="a", directory=tmp_path / "state")
    trained.save_sampler_weights(model_id="a", directory=tmp_path / "sampler")
    trained.create_adapter(model_id="resumed", rank=RANK, seed=3)
    trained.load_state(model_id="resumed", directory=tmp_path / "state", with_optimizer=True)
    assert torch.allclose(
        logprobs(trained=trained, model_id="resumed", row=row),
        logprobs(trained=trained, model_id="a", row=row),
    )
    config = json.loads((tmp_path / "sampler" / "adapter_config.json").read_text())
    assert config["r"] == RANK and config["lora_alpha"] == 2 * RANK
    keys = load_file(str(tmp_path / "sampler" / WEIGHTS_FILE)).keys()
    assert keys and not any(".a." in key or "visual" in key for key in keys)


def test_a_loss_without_its_inputs_is_refused() -> None:
    trained = trainer()
    trained.create_adapter(model_id="a", rank=RANK, seed=1)
    row = rl_row(advantage=1.0)._replace(advantages=None)
    with pytest.raises(ValueError, match="advantages"):
        trained.forward_backward(
            model_id="a", rows=[row], loss_fn="cispo", loss_fn_config=CISPO, backward=True
        )
