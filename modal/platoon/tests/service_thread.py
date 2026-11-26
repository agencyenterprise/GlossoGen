"""The Tinker-API service with CPU backends, served on a local port from a thread of the test
process.

The service samples with a script over the toy tokenizer and trains a unigram model, so a test can
point the real Tinker SDK, and ``platoon train``, at its URL. It runs in a thread with an event loop
of its own, because ``platoon train`` runs its own loop in the main thread.
"""

import asyncio
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from aiohttp import web
from platoon.testing import toy_tokenizer
from tinker_service.adapter_trainer import AdapterTrainer
from tinker_service.app import build_app
from tinker_service.checkpoints import CheckpointStore
from tinker_service.scripted_backend import ScriptedSampler
from tinker_service.service import ServiceSettings, TinkerService
from tinker_service.unigram_backend import UnigramModel

HOST = "127.0.0.1"
API_KEY = "tml-glossogen-platoon-tests"
SAMPLED_LOGPROB = -0.25
PROMPT_LOGPROB = -0.5
STOP_TOKEN = "<|im_end|>"
STARTUP_SECONDS = 30.0


class RunningService(NamedTuple):
    """A service that a thread serves: its base URL and the objects behind it."""

    url: str
    service: TinkerService
    sampler: ScriptedSampler
    model: UnigramModel


def cpu_service(*, base_model: str, script: Callable[[str], str], root: Path) -> TinkerService:
    """A service of ``base_model`` with a scripted sampler and a unigram trainer over the toy
    tokenizer."""
    tokenizer = toy_tokenizer()
    sampler = ScriptedSampler(
        tokenizer=tokenizer,
        script=script,
        stop_token=STOP_TOKEN,
        logprob=SAMPLED_LOGPROB,
        prompt_logprob=PROMPT_LOGPROB,
    )
    model = UnigramModel(vocab_size=len(tokenizer))
    return TinkerService(
        trainer=AdapterTrainer(model=model, base_model=base_model),
        sampler=sampler,
        checkpoints=CheckpointStore(root=root),
        settings=ServiceSettings(
            base_model=base_model, published_per_model=6, on_saved=lambda: None
        ),
    )


class ServerThread(threading.Thread):
    """A thread that serves an aiohttp app on a free port until it is told to stop."""

    def __init__(self, *, app: web.Application) -> None:
        super().__init__(daemon=True)
        self.app = app
        self.loop = asyncio.new_event_loop()
        self.started_event = threading.Event()
        self.stopped = asyncio.Event()
        self.port = 0

    def run(self) -> None:
        """Serve until ``stop``."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.serve())

    async def serve(self) -> None:
        """Start the site, report its port, and wait for the stop."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host=HOST, port=0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.started_event.set()
        await self.stopped.wait()
        await runner.cleanup()

    def stop(self) -> None:
        """Ask the server to stop, and wait for the thread."""
        self.loop.call_soon_threadsafe(self.stopped.set)
        self.join()


@contextmanager
def running_service(
    *, base_model: str, script: Callable[[str], str], root: Path
) -> Iterator[RunningService]:
    """Serve a CPU service while the block runs."""
    service = cpu_service(base_model=base_model, script=script, root=root)
    thread = ServerThread(app=build_app(service=service, api_key=API_KEY))
    thread.start()
    if not thread.started_event.wait(timeout=STARTUP_SECONDS):
        raise RuntimeError("the service did not start")
    try:
        yield RunningService(
            url=f"http://{HOST}:{thread.port}",
            service=service,
            sampler=service.sampler,  # type: ignore[arg-type]
            model=service.trainer.model,  # type: ignore[arg-type]
        )
    finally:
        thread.stop()
