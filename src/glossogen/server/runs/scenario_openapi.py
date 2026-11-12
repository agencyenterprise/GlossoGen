"""The parts of the API schema that depend on which scenarios this server loaded.

``RunDetailResponse.scenario_extras`` holds one scenario's extras, and the live
event stream carries the platform's SSE events plus those scenarios add. The
response models type both without naming any scenario, so they import before
the scenario catalog has loaded. :func:`publish_scenario_schemas` is called by
the app factory, once the catalog has loaded: it makes the app's OpenAPI schema
describe ``scenario_extras`` as the discriminated union of every loaded
scenario's extras model, and the stream as the union of every SSE event model.

Schemas are JSON documents, and FastAPI's ``openapi()`` returns one as a dict, so
the functions here take and return dicts rather than models.
"""

import json
import re
from collections.abc import Mapping
from typing import Annotated, Any, Union

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel, Discriminator

from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension
from glossogen.server.runs.models import PLATFORM_SSE_EVENT_TYPES

_REF_PREFIX = "#/components/schemas/"
_DETAIL_PATH = "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}"
_EVENTS_PATH = "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/events"
_EXTRAS_FIELD = "scenario_extras"
_EXTRAS_PROBE_PATH = "/scenario-extras-probe"
_EVENTS_PROBE_PATH = "/scenario-events-probe"


def publish_scenario_schemas(
    app: FastAPI, extensions: Mapping[str, ScenarioRunDetailExtension]
) -> None:
    """Make ``app``'s OpenAPI schema describe the extras and SSE events of ``extensions``.

    Replaces ``app.openapi`` with a builder that generates the app's schema the way
    FastAPI does, from the same settings, over its routes plus two probe routes
    that respond with the scenario unions. Generating them in one pass gives every
    model one name across the whole schema, as FastAPI disambiguates them. The
    probe routes are then removed and their unions moved where they belong. The
    schema is built once, on first request, and cached on the app as FastAPI
    caches it.
    """
    probe_routes = _probe_routes(extensions=extensions)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = _build_schema(app=app, probe_routes=probe_routes)
        return app.openapi_schema

    app.openapi = openapi  # pyright: ignore[reportAttributeAccessIssue]


def _probe_routes(extensions: Mapping[str, ScenarioRunDetailExtension]) -> list[APIRoute]:
    """Return routes whose responses are the extras union, if any, and the SSE event union."""
    routes: list[APIRoute] = []
    extras_models = tuple(extension.extras_model_cls for extension in extensions.values())
    if extras_models:
        extras_union: Any = Union[extras_models]
        extras_form: Any = Annotated[extras_union, Discriminator("scenario_name")]
        routes.append(
            APIRoute(
                path=_EXTRAS_PROBE_PATH,
                endpoint=_probe_endpoint,
                response_model=extras_form | None,
                methods=["GET"],
            )
        )
    sse_models: tuple[type[BaseModel], ...] = (
        *PLATFORM_SSE_EVENT_TYPES,
        *(cls for extension in extensions.values() for cls in extension.sse_event_classes),
    )
    sse_union: Any = Union[sse_models]
    routes.append(
        APIRoute(
            path=_EVENTS_PROBE_PATH,
            endpoint=_probe_endpoint,
            response_model=None,
            responses={200: {"model": Annotated[sse_union, Discriminator("event_type")]}},
            methods=["GET"],
        )
    )
    return routes


async def _probe_endpoint() -> None:
    """Stand in for the probe routes, which are only described, never served."""


def _build_schema(app: FastAPI, probe_routes: list[APIRoute]) -> dict[str, Any]:
    """Generate ``app``'s schema with the probe routes, then move their unions into place."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        summary=app.summary,
        description=app.description,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
        routes=[*app.routes, *probe_routes],
        webhooks=app.webhooks.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        separate_input_output_schemas=app.separate_input_output_schemas,
        external_docs=app.openapi_external_docs,
    )
    paths: dict[str, Any] = schema["paths"]
    components: dict[str, Any] = schema["components"]["schemas"]
    # FastAPI publishes some components no path reaches; only those this step
    # leaves unreached, such as the extras base class, are removed.
    unreached_before = _unreachable_components(schema=schema)
    if _EXTRAS_PROBE_PATH in paths:
        detail_ref: str = _response_schema(schema=schema, path=_DETAIL_PATH)["$ref"]
        detail = components[detail_ref.removeprefix(_REF_PREFIX)]
        detail["properties"][_EXTRAS_FIELD] = {
            **_response_schema(schema=schema, path=_EXTRAS_PROBE_PATH),
            # Pydantic's default title for the field.
            "title": _EXTRAS_FIELD.replace("_", " ").title(),
        }
        del paths[_EXTRAS_PROBE_PATH]
    events = _response_schema(schema=schema, path=_EVENTS_PATH)
    events.update(
        {**_response_schema(schema=schema, path=_EVENTS_PROBE_PATH), "title": events["title"]}
    )
    del paths[_EVENTS_PROBE_PATH]
    for name in _unreachable_components(schema=schema) - unreached_before:
        del components[name]
    return schema


def _response_schema(schema: dict[str, Any], path: str) -> dict[str, Any]:
    """Return the JSON schema of the 200 response of ``GET path`` in ``schema``."""
    return schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def _unreachable_components(schema: dict[str, Any]) -> set[str]:
    """Return the names of the components no path's schema reaches."""
    components: dict[str, Any] = schema["components"]["schemas"]
    reachable: set[str] = set()
    pending = _referenced_names(node=schema["paths"])
    while pending:
        name = pending.pop()
        if name in reachable or name not in components:
            continue
        reachable.add(name)
        pending |= _referenced_names(node=components[name])
    return set(components) - reachable


def _referenced_names(node: Any) -> set[str]:
    """Return the component names every ``$ref`` under ``node`` points at."""
    return set(re.findall(r'"\$ref": "#/components/schemas/([^"]+)"', json.dumps(node)))
