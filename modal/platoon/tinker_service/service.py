"""The state and the operations of the Tinker-API service: sessions, trained adapters, sampling
sessions, futures.

Each Tinker training client is one model id, one adapter of the trainer. Training operations run one
at a time, in the order they arrive, in a worker thread: the SDK sends a client's requests in order,
and the GPU trains one batch at a time. Sampling runs at the same time as training.

``save_weights_for_sampler`` saves the adapter, publishes it to the sampler under the name ``<model
id>-<name>``, and, for an unnamed save, opens a sampling session on it. The sampler keeps the newest
``published_per_model`` adapters of each model id loaded and retires older ones, so it should exceed
the run's ``max_staleness`` + 1. ``on_saved`` runs after every save, for example to commit a Modal
volume.
"""

import asyncio
import logging
import uuid
from collections import deque
from collections.abc import Callable
from typing import NamedTuple

from pydantic import BaseModel
from tinker import types
from tinker_service.adapter_trainer import AdapterTrainer
from tinker_service.checkpoints import (
    CheckpointKind,
    CheckpointPath,
    CheckpointStore,
    parse_path,
    tinker_path,
)
from tinker_service.futures import FutureStore
from tinker_service.sampling import SamplingBackend
from tinker_service.wire import (
    adam_settings,
    forward_backward_output,
    sample_response,
    sampling_request,
    training_row,
)

logger = logging.getLogger(__name__)


class ServiceSettings(NamedTuple):
    """The service's base model, how many adapters of each model id stay published, and the save
    hook."""

    base_model: str
    published_per_model: int
    on_saved: Callable[[], None]


class TinkerService:
    """The service behind the HTTP routes of ``tinker_service.app``."""

    def __init__(
        self,
        *,
        trainer: AdapterTrainer,
        sampler: SamplingBackend,
        checkpoints: CheckpointStore,
        settings: ServiceSettings,
    ) -> None:
        self.trainer = trainer
        self.sampler = sampler
        self.checkpoints = checkpoints
        self.settings = settings
        self.futures = FutureStore()
        self.training_lock = asyncio.Lock()
        self.sessions: set[str] = set()
        self.sampling_sessions: dict[str, str | None] = {}
        self.published: dict[str, deque[str]] = {}
        self.sampler_saves: dict[str, int] = {}

    def create_session(self, *, request: types.CreateSessionRequest) -> types.CreateSessionResponse:
        """Open a session; the service keeps no state per session beyond its id."""
        del request
        session_id = f"session-{uuid.uuid4().hex}"
        self.sessions.add(session_id)
        return types.CreateSessionResponse(session_id=session_id)

    def check_base_model(self, *, base_model: str | None) -> None:
        """Refuse a base model that the service does not serve."""
        if base_model is not None and base_model != self.settings.base_model:
            raise ValueError(f"this service serves {self.settings.base_model}, not {base_model}")

    async def trained(self, *, work: Callable[[], BaseModel]) -> BaseModel:
        """Run a training operation in a worker thread, after the ones that arrived before it."""
        async with self.training_lock:
            return await asyncio.to_thread(work)

    def create_model(self, *, request: types.CreateModelRequest) -> types.UntypedAPIFuture:
        """Start adding an adapter for a new model id."""
        self.check_base_model(base_model=request.base_model)
        if request.lora_config is None:
            raise ValueError("the service trains LoRA adapters only; lora_config is required")
        lora = request.lora_config
        model_id = f"model-{uuid.uuid4().hex[:12]}"

        def work() -> BaseModel:
            self.trainer.create_adapter(model_id=model_id, rank=lora.rank, seed=lora.seed)
            return types.CreateModelResponse(model_id=model_id)

        request_id = self.futures.submit(work=self.trained(work=work))
        return types.UntypedAPIFuture(request_id=request_id, model_id=model_id)

    def forward_backward(self, *, request: types.ForwardBackwardRequest) -> types.UntypedAPIFuture:
        """Start computing the rows' logprobs and losses, and adding their gradient."""
        batch = request.forward_backward_input
        rows = [training_row(datum=datum) for datum in batch.data]
        loss_fn_config: dict[str, float] = {}
        if batch.loss_fn_config is not None:
            loss_fn_config = dict(batch.loss_fn_config)

        def work() -> BaseModel:
            outputs = self.trainer.forward_backward(
                model_id=request.model_id,
                rows=rows,
                loss_fn=batch.loss_fn,
                loss_fn_config=loss_fn_config,
                backward=True,
            )
            return forward_backward_output(outputs=outputs)

        request_id = self.futures.submit(work=self.trained(work=work))
        return types.UntypedAPIFuture(request_id=request_id, model_id=request.model_id)

    def optim_step(self, *, request: types.OptimStepRequest) -> types.UntypedAPIFuture:
        """Start an optimizer step of the model id's adapter."""
        adam = adam_settings(params=request.adam_params)

        def work() -> BaseModel:
            metrics = self.trainer.optim_step(model_id=request.model_id, adam=adam)
            return types.OptimStepResponse(metrics=metrics)

        request_id = self.futures.submit(work=self.trained(work=work))
        return types.UntypedAPIFuture(request_id=request_id, model_id=request.model_id)

    def save_weights(self, *, request: types.SaveWeightsRequest) -> types.UntypedAPIFuture:
        """Start saving the adapter and its optimizer state as a full checkpoint."""
        if request.path is None:
            raise ValueError("save_weights needs a name")
        checkpoint = CheckpointPath(
            model_id=request.model_id, kind=CheckpointKind.WEIGHTS, name=request.path
        )

        def work() -> BaseModel:
            folder = self.checkpoints.folder(checkpoint=checkpoint)
            self.trainer.save_state(model_id=request.model_id, directory=folder)
            self.checkpoints.write_info(
                checkpoint=checkpoint, info=self.trainer.info(model_id=request.model_id)
            )
            self.settings.on_saved()
            return types.SaveWeightsResponse(path=tinker_path(checkpoint=checkpoint))

        request_id = self.futures.submit(work=self.trained(work=work))
        return types.UntypedAPIFuture(request_id=request_id, model_id=request.model_id)

    def sampler_checkpoint(self, *, model_id: str, name: str | None) -> CheckpointPath:
        """The checkpoint of a sampler save: its name, or the next ``sampler-<n>`` of an unnamed
        save."""
        if name is None:
            count = self.sampler_saves.get(model_id, 0) + 1
            self.sampler_saves[model_id] = count
            name = f"sampler-{count}"
        return CheckpointPath(model_id=model_id, kind=CheckpointKind.SAMPLER, name=name)

    def save_weights_for_sampler(
        self, *, request: types.SaveWeightsForSamplerRequest
    ) -> types.UntypedAPIFuture:
        """Start saving the adapter for the sampler, publishing it, and, unnamed, opening a session
        on it."""
        checkpoint = self.sampler_checkpoint(model_id=request.model_id, name=request.path)

        def save() -> BaseModel:
            folder = self.checkpoints.folder(checkpoint=checkpoint)
            self.trainer.save_sampler_weights(model_id=request.model_id, directory=folder)
            self.checkpoints.write_info(
                checkpoint=checkpoint, info=self.trainer.info(model_id=request.model_id)
            )
            self.settings.on_saved()
            return types.SaveWeightsForSamplerResponse(path=tinker_path(checkpoint=checkpoint))

        async def work() -> BaseModel:
            await self.trained(work=save)
            adapter = await self.publish(checkpoint=checkpoint)
            if request.path is not None:
                return types.SaveWeightsForSamplerResponseInternal(
                    path=tinker_path(checkpoint=checkpoint), type="save_weights_for_sampler"
                )
            session_id = self.open_sampling_session(adapter=adapter)
            return types.SaveWeightsForSamplerResponseInternal(
                sampling_session_id=session_id, type="save_weights_for_sampler"
            )

        request_id = self.futures.submit(work=work())
        return types.UntypedAPIFuture(request_id=request_id, model_id=request.model_id)

    async def publish(self, *, checkpoint: CheckpointPath) -> str:
        """Load a sampler checkpoint into the sampler, retire the oldest beyond the window, and
        return its name."""
        adapter = f"{checkpoint.model_id}-{checkpoint.name}"
        published = self.published.setdefault(checkpoint.model_id, deque())
        if adapter in published:
            return adapter
        await self.sampler.publish(
            adapter=adapter, directory=self.checkpoints.folder(checkpoint=checkpoint)
        )
        published.append(adapter)
        while len(published) > self.settings.published_per_model:
            await self.sampler.retire(adapter=published.popleft())
        return adapter

    def open_sampling_session(self, *, adapter: str | None) -> str:
        """A new sampling session on ``adapter``, or on the base model when it is None."""
        session_id = f"sampling-{uuid.uuid4().hex}"
        self.sampling_sessions[session_id] = adapter
        return session_id

    def load_weights(self, *, request: types.LoadWeightsRequest) -> types.UntypedAPIFuture:
        """Start loading a full checkpoint into the model id's adapter."""
        checkpoint = parse_path(path=request.path)
        if checkpoint.kind != CheckpointKind.WEIGHTS:
            raise ValueError(f"{request.path} is not a full checkpoint")

        def work() -> BaseModel:
            self.trainer.load_state(
                model_id=request.model_id,
                directory=self.checkpoints.folder(checkpoint=checkpoint),
                with_optimizer=request.optimizer,
            )
            return types.LoadWeightsResponse(path=request.path, type="load_weights")

        request_id = self.futures.submit(work=self.trained(work=work))
        return types.UntypedAPIFuture(request_id=request_id, model_id=request.model_id)

    def weights_info(self, *, path: str) -> types.WeightsInfoResponse:
        """The base model and rank of a checkpoint."""
        info = self.checkpoints.read_info(checkpoint=parse_path(path=path))
        return types.WeightsInfoResponse(
            base_model=info.base_model, is_lora=True, lora_rank=info.rank
        )

    async def create_sampling_session(
        self, *, request: types.CreateSamplingSessionRequest
    ) -> types.CreateSamplingSessionResponse:
        """A sampling session on a sampler checkpoint, or on the base model."""
        if request.model_path is None:
            self.check_base_model(base_model=request.base_model)
            return types.CreateSamplingSessionResponse(
                sampling_session_id=self.open_sampling_session(adapter=None)
            )
        checkpoint = parse_path(path=request.model_path)
        if checkpoint.kind != CheckpointKind.SAMPLER:
            raise ValueError(f"{request.model_path} is not a sampler checkpoint")
        adapter = await self.publish(checkpoint=checkpoint)
        return types.CreateSamplingSessionResponse(
            sampling_session_id=self.open_sampling_session(adapter=adapter)
        )

    def sample(self, *, request: types.SampleRequest) -> types.UntypedAPIFuture:
        """Start sampling from the request's sampling session."""
        if request.sampling_session_id is None:
            raise ValueError("asample needs a sampling_session_id")
        if request.sampling_session_id not in self.sampling_sessions:
            raise ValueError(f"unknown sampling session {request.sampling_session_id!r}")
        adapter = self.sampling_sessions[request.sampling_session_id]
        decoded = sampling_request(request=request)

        async def work() -> BaseModel:
            result = await self.sampler.sample(adapter=adapter, request=decoded)
            return sample_response(result=result)

        return types.UntypedAPIFuture(request_id=self.futures.submit(work=work()))

    async def delete_checkpoint(self, *, checkpoint: CheckpointPath) -> None:
        """Delete a checkpoint, retiring its adapter first when the sampler holds it."""
        adapter = f"{checkpoint.model_id}-{checkpoint.name}"
        published = self.published.get(checkpoint.model_id, deque())
        if checkpoint.kind == CheckpointKind.SAMPLER and adapter in published:
            published.remove(adapter)
            await self.sampler.retire(adapter=adapter)
        self.checkpoints.delete(checkpoint=checkpoint)
