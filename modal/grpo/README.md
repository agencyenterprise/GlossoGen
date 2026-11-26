# `modal/grpo/` — reinforcement learning on signal_game

With the code in this folder, you can train Qwen3.8-27B by reinforcement learning on
signal_game, with GRPO and a LoRA adapter. The trainer, and the vLLM server that serves each
new adapter, run on Modal. The loop that plays the games runs on your machine.
[Training a model with RL](../../docs/rl-training.md) gives the commands for a training run and
the results of our runs.

| File | What it holds |
| --- | --- |
| `grpo_app.py` | The Modal app: the trainer, and the vLLM server that serves each new adapter |
| `grpo_loop.py` | The loop: load an adapter, play games, score them, and send the training sequences to the trainer |
| `grpo_training.py` | The GRPO loss, the LoRA setup, and saving and loading an adapter |
| `grpo_records.py` | The records that the loop and the trainer exchange, and the base model's name |
| `partner.py` | The frozen partner: the model of a seat that does not train |
| `base_model_partner.json` | A partner file that puts the base model in `player_b` |
| `signal_game_rewards.py` | The signal_game rewards, `win` and `first_item` |
| `first_item_baselines.py` | The random-square and start-square baselines of `first_item`, per step |
| `token_sequences.py` | Training sequences from the token ids that a game logged |
| `signal_game_shapes.json` | The game config: shapes on a 3×3 grid, 10 rounds, `record_token_ids` on |
| `test_grpo_loop.py` | Tests of the rewards, the advantages, the sequences and the game config, and a check that the Modal modules parse as Python 3.12 |
| `test_partner.py` | Tests of the partner file, the partner's game config and URLs, and the seats that train |
| `test_grpo_training.py` | CPU tests of the loss, the k3 clamp, the LoRA targets and reloading a saved adapter, on a tiny random model |

The repository's test suite does not run these tests. Run the loop's tests with:

```bash
VIRTUAL_ENV= uv run --no-sync pytest modal/grpo/
```

The tests in `test_grpo_training.py` need torch, transformers and peft, which the repository's
environment does not install. `conftest.py` leaves them out when torch is missing, and the
report header says so. Run them in a throwaway environment:

```bash
uv run --no-project --python 3.12 --with torch==2.15.0 --with transformers==5.22.1 \
  --with peft==0.21.2 --with safetensors==0.8.0 --with accelerate==1.15.0 --with pytest \
  python -m pytest modal/grpo/test_grpo_training.py -p no:cacheprovider
```
