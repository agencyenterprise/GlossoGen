# `modal/platoon/` — reinforcement learning on signal_game with platoon

The code in this folder trains Qwen3.8-27B on signal_game by reinforcement learning, with
[platoon](https://github.com/ApGa/platoon) 0.6.0. Platoon plays the games and computes the
advantages on your machine. It sends each batch to a training service that implements the Tinker
API. The service in `tinker_service/` runs on Modal. [Training a model with RL](../../docs/rl-training.md)
gives the commands and explains how the parts fit together.

This folder is a uv project of its own. Platoon pins tinker-cookbook below 0.4. That
tinker-cookbook needs a transformers release that needs huggingface-hub below 2, and GlossoGen
needs huggingface-hub 2.4 or later. So platoon cannot share GlossoGen's environment. The games
and the scorer run in the repository's environment, as subprocesses.

| Path | What it holds |
| --- | --- |
| `glossogen_platoon/` | The platoon side: the harness that plays one game per episode, the episode program, the per-round credit estimator, the task table writer and the evaluation report |
| `glossogen_side/` | Code that runs in GlossoGen's environment: the game scorer, the signal_game rewards and the first-item baselines |
| `tinker_service/` | The Tinker-API service: its HTTP routes, its state, the PEFT trainer, the vLLM sampler, and the CPU backends that the tests use |
| `platoon_app.py` | The Modal app that runs the service on two H200 GPUs |
| `configs/` | The training configs, the signal_game config and the task table |
| `tests/` | CPU tests with scripted players |

## Set up

Install the repository's environment first, because the harness runs each game with it:

```bash
make install                     # from the repository root
cd modal/platoon
VIRTUAL_ENV= uv sync             # this project's environment, in modal/platoon/.venv
```

## Run the tests

```bash
cd modal/platoon
VIRTUAL_ENV= uv run --no-sync pytest
```

The tests run on a CPU and need no network and no API key. They play real GlossoGen games, in
which a script writes the players' answers in place of a model. They check:

- the episodes: one span per round for each seat, and a seat outside platoon that platoon neither
  mints nor records (`test_episodes.py`);
- the credit estimator against the rule that each round's score minus the seat's mean in that
  round is the advantage, the KL penalty and the KL limit (`test_credit.py`);
- the Tinker-API service, driven over HTTP by the Tinker SDK that platoon uses
  (`test_tinker_service.py`);
- the PEFT trainer on a tiny random model of Qwen3.8-27B's architecture (`test_peft_model.py`);
- the vLLM sampler against a stand-in server (`test_vllm_backend.py`);
- `platoon train` end to end with each of the three configs, against the service with CPU
  backends (`test_train.py`);
- that the code shipped to the Modal image parses as Python 3.12 (`test_modal_app.py`).

The repository's own test suite does not run these tests.
