"""The API schema describes the extras and live events of the scenarios the app was built with.

The response models name no scenario, so they import before any catalog loads.
The schema the frontend's types are generated from is completed by the app
factory from the catalog current at that time.
"""

from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.catalog import (
    ScenarioCatalog,
    current_scenario_catalog,
)
from glossogen.scenario_contract.run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenario_contract.run_detail_types import AgentDetail as PlatformAgentDetail
from glossogen.scenario_contract.run_detail_types import ChannelMessage
from glossogen.scenarios.veyru.scenario import VeyruScenario
from glossogen.server.runs.models import PLATFORM_SSE_EVENT_TYPES, RunDetailResponse
from glossogen.server.runs.scenario_extension import collect_scenario_extensions, scenario_extension
from tests.fakes.catalog_installation import catalog_including, scenario_catalog_installed
from tests.fakes.external_scenario.run_detail_extension import ExternalScenarioRunExtras
from tests.fakes.external_scenario.scenario import ExternalScenario
from tests.fakes.local_app import build_local_app

EVENTS_PATH = "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/events"
EXTRAS_PREFIX = "#/components/schemas/"


def extras_union(schema: dict[str, Any]) -> dict[str, Any]:
    """The discriminated union ``scenario_extras`` is published as."""
    field = schema["components"]["schemas"]["RunDetailResponse"]["properties"]["scenario_extras"]
    union, nothing = field["anyOf"]
    assert nothing == {"type": "null"}
    return union


def events_union(schema: dict[str, Any]) -> dict[str, Any]:
    """The discriminated union the live event stream is published as."""
    response = schema["paths"][EVENTS_PATH]["get"]["responses"]["200"]
    return response["content"]["application/json"]["schema"]


def test_the_extras_union_holds_every_loaded_scenarios_extras(tmp_path: Path) -> None:
    schema = build_local_app(runs_dir=tmp_path).openapi()
    extensions = collect_scenario_extensions()

    union = extras_union(schema=schema)

    assert union["discriminator"]["propertyName"] == "scenario_name"
    assert union["discriminator"]["mapping"] == {
        name: f"{EXTRAS_PREFIX}{extension.extras_model_cls.__name__}"
        for name, extension in extensions.items()
    }
    for extension in extensions.values():
        assert extension.extras_model_cls.__name__ in schema["components"]["schemas"]
    assert "ScenarioRunExtrasBase" not in schema["components"]["schemas"]
    assert (
        schema["components"]["schemas"]["RunDetailResponse"]["properties"]["scenario_extras"][
            "title"
        ]
        == "Scenario Extras"
    )


def test_the_event_stream_union_holds_the_platform_and_scenario_events(tmp_path: Path) -> None:
    schema = build_local_app(runs_dir=tmp_path).openapi()
    scenario_events = [
        cls
        for extension in collect_scenario_extensions().values()
        for cls in extension.sse_event_classes
    ]

    union = events_union(schema=schema)

    published = {ref["$ref"].removeprefix(EXTRAS_PREFIX) for ref in union["oneOf"]}
    assert published == {cls.__name__ for cls in (*PLATFORM_SSE_EVENT_TYPES, *scenario_events)}
    assert scenario_events, "the built-ins publish scenario SSE events, so this is not vacuous"
    assert union["discriminator"]["propertyName"] == "event_type"
    assert union["title"].startswith("Response 200 Stream Run Events")


def test_a_scenario_loaded_before_the_app_is_built_is_in_its_schema(tmp_path: Path) -> None:
    """The union comes from the catalog at build time, not from what was imported first."""
    widened = catalog_including(
        base=current_scenario_catalog(), name="external_scenario", scenario_cls=ExternalScenario
    )

    with scenario_catalog_installed(catalog=widened):
        schema = build_local_app(runs_dir=tmp_path).openapi()
    without = build_local_app(runs_dir=tmp_path).openapi()

    assert "external_scenario" in extras_union(schema=schema)["discriminator"]["mapping"]
    assert ExternalScenarioRunExtras.__name__ in schema["components"]["schemas"]
    assert "external_scenario" not in extras_union(schema=without)["discriminator"]["mapping"]


def test_the_schema_is_built_once_per_app(tmp_path: Path) -> None:
    app = build_local_app(runs_dir=tmp_path)

    assert app.openapi() is app.openapi()


def test_extras_serialize_as_the_scenarios_own_model() -> None:
    """The field is typed as the base; its serialization keeps the subclass's fields."""
    extras = ExternalScenarioRunExtras(message_count=3)

    dumped = RunDetailResponse.__pydantic_serializer__.to_python(
        RunDetailResponse.model_construct(scenario_extras=extras),
        include={"scenario_extras"},
        warnings=False,
    )
    assert dumped == {"scenario_extras": {"scenario_name": "external_scenario", "message_count": 3}}


def test_the_run_detail_extension_is_looked_up_by_the_runs_scenario() -> None:
    """Run detail asks per run; a scenario this process cannot load renders without extras."""
    veyru = scenario_extension(scenario_name="veyru")

    assert veyru is not None
    assert veyru.extras_model_cls.model_fields["scenario_name"].default == "veyru"
    assert scenario_extension(scenario_name="not_loaded_here") is None


def test_with_no_scenario_extras_the_field_keeps_the_base_schema(tmp_path: Path) -> None:
    """A server whose scenarios declare no extension still publishes a valid schema."""
    with scenario_catalog_installed(catalog=ScenarioCatalog(scenarios={}, loaded_sources=())):
        schema = build_local_app(runs_dir=tmp_path).openapi()

    field = schema["components"]["schemas"]["RunDetailResponse"]["properties"]["scenario_extras"]
    assert field["anyOf"][0] == {"$ref": f"{EXTRAS_PREFIX}ScenarioRunExtrasBase"}
    assert "ScenarioRunExtrasBase" in schema["components"]["schemas"]
    published = {
        ref["$ref"].removeprefix(EXTRAS_PREFIX) for ref in events_union(schema=schema)["oneOf"]
    }
    assert published == {cls.__name__ for cls in PLATFORM_SSE_EVENT_TYPES}


class AgentDetail(ScenarioRunExtrasBase):
    """Extras sharing its class name with a platform response model."""

    scenario_name: Literal["collision"] = "collision"
    custom_field: int


class CollidingExtension(ScenarioRunDetailExtension):
    """Declares the colliding extras model."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = AgentDetail
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, PlatformAgentDetail],
        messages: list[ChannelMessage],
    ) -> ScenarioRunExtrasBase:
        _ = events, agents_by_id, messages
        return AgentDetail(custom_field=0)


class CollidingScenario(VeyruScenario):
    """A scenario whose extras model is named like a platform model."""

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        return CollidingExtension()


def test_a_scenario_model_named_like_a_platform_model_gets_its_own_component(
    tmp_path: Path,
) -> None:
    """Both models keep their own schema; neither reference lands on the other's fields."""
    widened = catalog_including(
        base=current_scenario_catalog(), name="collision", scenario_cls=CollidingScenario
    )

    with scenario_catalog_installed(catalog=widened):
        schema = build_local_app(runs_dir=tmp_path).openapi()

    components = schema["components"]["schemas"]
    extras_ref = extras_union(schema=schema)["discriminator"]["mapping"]["collision"]
    assert "custom_field" in components[extras_ref.removeprefix(EXTRAS_PREFIX)]["properties"]
    detail = components["RunDetailResponse"]["properties"]["agents"]["items"]["$ref"]
    assert "agent_id" in components[detail.removeprefix(EXTRAS_PREFIX)]["properties"]
    assert extras_ref != detail
