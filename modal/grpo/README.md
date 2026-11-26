# `modal/grpo/` — reinforcement learning on signal_game

With the code in this folder, you can train Qwen3.8-27B by reinforcement learning on
signal_game, with GRPO and a LoRA adapter. The trainer, and the vLLM server that serves each
new adapter, run on Modal. The loop that plays the games runs on your machine.
[Training a model with RL](../../docs/rl-training.md) gives the commands for a training run and
the results of our runs.

| File | What it holds |
| --- | --- |
| `grpo_app.py` | The Modal app: the trainer, and the vLLM server that serves each new adapter |
| `adapter_loader.py` | The policy server's loader: load an adapter, then unload the ones that a request does not keep |
| `trained_adapters.py` | The games that each saved adapter trained on, so that a step trains on its games once |
| `grpo_training.py` | The GRPO loss with its capped importance ratio, the LoRA setup, and saving and loading an adapter |
| `grpo_records.py` | The records that the loop and the trainer exchange, and the base model's name |
| `grpo_loop.py` | The loop's command line, and the order of a step: load an adapter, play games, train, record |
| `loop_services.py` | The loop's view of the Modal app and of `glossogen run`, and their implementations |
| `game_sets.py` | A step's or a test's games: their seed configs, logs and labels, played a few at a time |
| `game_ledger.py` | The games that ended, which a resumed step reuses, and the games that a stop cut off |
| `step_batch.py` | A step's finished games, their advantages, and the training batch |
| `loop_records.py` | The lines of `steps.jsonl` and `eval.jsonl` |
| `partner.py` | The frozen partner: the model of a seat that does not train |
| `base_model_partner.json` | A partner file that puts the base model in `player_b` |
| `signal_game_rewards.py` | The signal_game rewards, `win` and `first_item` |
| `first_item_baselines.py` | The random-square and start-square baselines of `first_item`, per step |
| `token_sequences.py` | Training sequences from the token ids that a game logged |
| `signal_game_shapes.json` | The game config: shapes on a 3×3 grid, 10 rounds, `record_token_ids` on, `self_hosted_strict_tools` off |
| `loop_fakes.py` | Fakes of the app and of `glossogen run` for the step tests: a fake policy server and trainer, and scripted players whose answers carry token ids |
| `test_grpo_loop.py` | Tests of the rewards, the advantages, the sequences and the game config, and a check that the Modal modules parse as Python 3.12 |
| `test_partner.py` | Tests of the partner file, the partner's game config and URLs, and the seats that train |
| `test_grpo_steps.py` | Whole training steps on CPU, with and without `--overlap`, tests during training, and runs that stop and resume: real signal_game games with scripted players, a fake app |
| `test_grpo_training.py` | CPU tests of the loss, the k3 clamp, the ratio cap, the LoRA targets and reloading a saved adapter, on a tiny random model |
| `design_notes.md` | Designs of two features that the loop does not have: a trained adapter for each seat, and a new game in each free slot |

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
