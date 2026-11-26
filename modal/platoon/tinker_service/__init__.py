"""A self-hosted service that implements the part of the Tinker API that platoon's training calls.

``app`` serves the HTTP routes that the Tinker SDK calls, ``service`` holds the sessions, the
trained adapters, the sampling sessions and the futures, and ``checkpoints`` maps ``tinker://``
paths to folders. Behind the service, a training backend computes logprobs and losses and steps each
adapter's optimizer (``adapter_trainer``, over ``peft_model`` on a GPU or ``unigram_backend`` on a
CPU), and a sampling backend samples (``vllm_backend`` on a GPU, ``scripted_backend`` on a CPU).
"""
