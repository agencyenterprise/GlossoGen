"""The parts of the API schema that depend on which scenarios this server loaded.

``RunDetailResponse.scenario_extras`` holds one scenario's extras, and the live
event stream carries the platform's SSE events plus those scenarios add. The
response models type both without naming any scenario, so they import before
the scenario catalog has loaded. :func:`publish_scenario_schemas` is called by
the app factory, once the catalog has loaded: it makes the app's OpenAPI schema
describe ``scenario_extras`` as the discriminated union of every loaded
scenario's extras model, and the stream as the union of every SSE event model.
"""

import json
from collections.abc import Mapping
from typing import Annotated, Any, Union

from fastapi import FastAPI
from pydantic import BaseModel, Discriminator

from glossogen.scenario_contract.run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.server.runs.models import PLATFORM_SSE_EVENT_TYPES, RunDetailResponse

_REF_TEMPLATE = "#/components/schemas/{model}"
_EVENTS_PATH = "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/events"
_EXTRAS_FIELD = "scenario_extras"
_EXTRAS_PROBE_PATH = "/scenario-extras"
_EVENTS_PROBE_PATH = "/scenario-events"


def publish_scenario_schemas(
    app: FastAPI, extensions: Mapping[str, ScenarioRunDetailExtension]
) -> None:
    """Make ``app``'s OpenAPI schema describe the extras and SSE events of ``extensions``.

    Wraps ``app.openapi`` so the schema FastAPI builds from the routes is
    completed the first time it is asked for, and cached as FastAPI caches it.
    """
    build_route_schema = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = build_route_schema()
        _add_scenario_unions(schema=schema, extensions=extensions)
        return schema

    app.openapi = openapi  # pyright: ignore[reportAttributeAccessIssue]


def _add_scenario_unions(
    schema: dict[str, Any], extensions: Mapping[str, ScenarioRunDetailExtension]
) -> None:
    """Replace the extras field and the event stream's schema with the scenario unions."""
    extras_models = tuple(extension.extras_model_cls for extension in extensions.values())
    sse_models = (
        *PLATFORM_SSE_EVENT_TYPES,
        *(cls for extension in extensions.values() for cls in extension.sse_event_classes),
    )
    probe = _probe_schema(extras_models=extras_models, sse_models=sse_models)
    components: dict[str, Any] = schema["components"]["schemas"]
    for name, definition in probe["components"]["schemas"].items():
        components.setdefault(name, definition)
    if extras_models:
        extras_schema = _response_schema(schema=probe, path=_EXTRAS_PROBE_PATH)
        properties = components[RunDetailResponse.__name__]["properties"]
        properties[_EXTRAS_FIELD] = {
            **extras_schema,
            # Pydantic's default title for the field.
            "title": _EXTRAS_FIELD.replace("_", " ").title(),
        }
    events_schema = _response_schema(schema=schema, path=_EVENTS_PATH)
    events_schema.update(
        {**_response_schema(schema=probe, path=_EVENTS_PROBE_PATH), "title": events_schema["title"]}
    )
    schema["components"]["schemas"] = dict(sorted(components.items()))
    _drop_unreferenced(schema=schema, name=ScenarioRunExtrasBase.__name__)


def _probe_schema(
    extras_models: tuple[type[ScenarioRunExtrasBase], ...],
    sse_models: tuple[type[BaseModel], ...],
) -> dict[str, Any]:
    """Return the OpenAPI schema of an app whose two routes respond with the scenario unions.

    Generating the unions through FastAPI, rather than through pydantic directly,
    gives them the same shape and key order as the rest of the schema.
    """
    probe = FastAPI()
    if extras_models:
        extras_union: Any = Union[extras_models]
        extras_form: Any = Annotated[extras_union, Discriminator("scenario_name")]
        probe.add_api_route(
            path=_EXTRAS_PROBE_PATH,
            endpoint=_probe_endpoint,
            response_model=extras_form | None,
            methods=["GET"],
        )
    sse_union: Any = Union[sse_models]
    probe.add_api_route(
        path=_EVENTS_PROBE_PATH,
        endpoint=_probe_endpoint,
        response_model=None,
        responses={200: {"model": Annotated[sse_union, Discriminator("event_type")]}},
        methods=["GET"],
    )
    return probe.openapi()


async def _probe_endpoint() -> None:
    """Stand in for the probe routes, which are only described, never served."""


def _response_schema(schema: dict[str, Any], path: str) -> dict[str, Any]:
    """Return the JSON schema of the 200 response of ``GET path`` in ``schema``."""
    return schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def _drop_unreferenced(schema: dict[str, Any], name: str) -> None:
    """Remove component ``name`` when nothing in ``schema`` refers to it any more."""
    components: dict[str, Any] = schema["components"]["schemas"]
    if name not in components:
        return
    reference = f'"$ref": {json.dumps(_REF_TEMPLATE.format(model=name))}'
    if reference not in json.dumps(schema):
        del components[name]
