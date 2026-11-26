"""The HTTP routes of the Tinker API that platoon's training calls, over a ``TinkerService``.

Every route but the health check needs the service's API key in the ``X-API-Key`` header, which the
Tinker SDK sends from ``TINKER_API_KEY``. A body the SDK's types refuse, or a request the service
refuses, answers 400 with the error. ``retrieve_future`` holds a pending request for up to
``RETRIEVE_WAIT_SECONDS`` and then answers 408, which the SDK takes as "ask again"; a failed future
answers 200 with ``error`` and ``category``, as the SDK expects.
"""

import logging
from collections.abc import Awaitable, Callable

from aiohttp import web
from pydantic import BaseModel, ValidationError
from tinker import types
from tinker_service.checkpoints import CheckpointKind, CheckpointPath
from tinker_service.futures import FutureStatus
from tinker_service.service import TinkerService

logger = logging.getLogger(__name__)

API = "/api/v1"
RETRIEVE_WAIT_SECONDS = 30.0
SERVICE_KEY = web.AppKey("service", TinkerService)
API_KEY = web.AppKey("api_key", str)
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def json_response(*, model: BaseModel) -> web.Response:
    """A response with ``model`` as JSON, unset fields left out."""
    return web.Response(
        text=model.model_dump_json(exclude_none=True), content_type="application/json"
    )


def error_response(*, status: int, message: str) -> web.Response:
    """An error with its HTTP status."""
    return web.json_response({"error": message}, status=status)


@web.middleware
async def checked(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Refuse a request without the API key, and turn a refused request into a 400."""
    if (
        request.path != f"{API}/healthz"
        and request.headers.get("X-API-Key") != request.app[API_KEY]
    ):
        return error_response(status=401, message="wrong or missing X-API-Key")
    try:
        return await handler(request)
    except (ValidationError, ValueError) as error:
        logger.exception("refused %s", request.path)
        return error_response(status=400, message=str(error))


def service_of(request: web.Request) -> TinkerService:
    """The service that the app serves."""
    return request.app[SERVICE_KEY]


async def healthz(request: web.Request) -> web.Response:
    """Whether the service is up."""
    del request
    return web.json_response({"status": "ok"})


async def create_session(request: web.Request) -> web.Response:
    """``POST /create_session``."""
    parsed = types.CreateSessionRequest.model_validate(await request.json())
    return json_response(model=service_of(request).create_session(request=parsed))


async def session_heartbeat(request: web.Request) -> web.Response:
    """``POST /session_heartbeat``: the service keeps sessions without heartbeats."""
    types.SessionHeartbeatRequest.model_validate(await request.json())
    return json_response(model=types.SessionHeartbeatResponse())


async def telemetry(request: web.Request) -> web.Response:
    """``POST /telemetry``: accepted and dropped."""
    await request.read()
    return json_response(model=types.TelemetryResponse(status="accepted"))


async def create_model(request: web.Request) -> web.Response:
    """``POST /create_model``."""
    parsed = types.CreateModelRequest.model_validate(await request.json())
    return json_response(model=service_of(request).create_model(request=parsed))


async def forward_backward(request: web.Request) -> web.Response:
    """``POST /forward_backward``."""
    parsed = types.ForwardBackwardRequest.model_validate(await request.json())
    return json_response(model=service_of(request).forward_backward(request=parsed))


async def optim_step(request: web.Request) -> web.Response:
    """``POST /optim_step``."""
    parsed = types.OptimStepRequest.model_validate(await request.json())
    return json_response(model=service_of(request).optim_step(request=parsed))


async def save_weights(request: web.Request) -> web.Response:
    """``POST /save_weights``."""
    parsed = types.SaveWeightsRequest.model_validate(await request.json())
    return json_response(model=service_of(request).save_weights(request=parsed))


async def save_weights_for_sampler(request: web.Request) -> web.Response:
    """``POST /save_weights_for_sampler``."""
    parsed = types.SaveWeightsForSamplerRequest.model_validate(await request.json())
    return json_response(model=service_of(request).save_weights_for_sampler(request=parsed))


async def load_weights(request: web.Request) -> web.Response:
    """``POST /load_weights``."""
    parsed = types.LoadWeightsRequest.model_validate(await request.json())
    return json_response(model=service_of(request).load_weights(request=parsed))


async def weights_info(request: web.Request) -> web.Response:
    """``POST /weights_info``."""
    body = await request.json()
    return json_response(model=service_of(request).weights_info(path=str(body["tinker_path"])))


async def create_sampling_session(request: web.Request) -> web.Response:
    """``POST /create_sampling_session``."""
    parsed = types.CreateSamplingSessionRequest.model_validate(await request.json())
    response = await service_of(request).create_sampling_session(request=parsed)
    return json_response(model=response)


async def asample(request: web.Request) -> web.Response:
    """``POST /asample``."""
    parsed = types.SampleRequest.model_validate(await request.json())
    return json_response(model=service_of(request).sample(request=parsed))


async def retrieve_future(request: web.Request) -> web.Response:
    """``POST /retrieve_future``: the result, the error, 408 while pending, or 410 for an unknown
    id."""
    parsed = types.FutureRetrieveRequest.model_validate(await request.json())
    state = await service_of(request).futures.retrieve(
        request_id=parsed.request_id, wait_seconds=RETRIEVE_WAIT_SECONDS
    )
    if state is None:
        return error_response(status=410, message=f"unknown request id {parsed.request_id}")
    if state.status == FutureStatus.PENDING:
        return web.json_response({"type": "try_again", "request_id": parsed.request_id}, status=408)
    if state.status == FutureStatus.FAILED or state.result is None:
        return web.json_response({"error": state.error, "category": state.category})
    return web.Response(text=state.result.model_dump_json(), content_type="application/json")


async def delete_checkpoint(request: web.Request) -> web.Response:
    """``DELETE /training_runs/{model_id}/checkpoints/{kind}/{name}``."""
    checkpoint = CheckpointPath(
        model_id=request.match_info["model_id"],
        kind=CheckpointKind(request.match_info["kind"]),
        name=request.match_info["name"],
    )
    await service_of(request).delete_checkpoint(checkpoint=checkpoint)
    return web.Response(status=204)


ROUTES: dict[str, Handler] = {
    "create_session": create_session,
    "session_heartbeat": session_heartbeat,
    "telemetry": telemetry,
    "create_model": create_model,
    "forward_backward": forward_backward,
    "optim_step": optim_step,
    "save_weights": save_weights,
    "save_weights_for_sampler": save_weights_for_sampler,
    "load_weights": load_weights,
    "weights_info": weights_info,
    "create_sampling_session": create_sampling_session,
    "asample": asample,
    "retrieve_future": retrieve_future,
}


def build_app(*, service: TinkerService, api_key: str) -> web.Application:
    """The aiohttp application that serves ``service`` to clients that send ``api_key``."""
    app = web.Application(middlewares=[checked], client_max_size=1024**3)
    app[SERVICE_KEY] = service
    app[API_KEY] = api_key
    app.router.add_get(f"{API}/healthz", healthz)
    for name, handler in ROUTES.items():
        app.router.add_post(f"{API}/{name}", handler)
    app.router.add_delete(
        f"{API}/training_runs/{{model_id}}/checkpoints/{{kind}}/{{name}}", delete_checkpoint
    )
    return app
