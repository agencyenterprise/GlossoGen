"""Auto-discovered scenario hooks for the run-detail API.

Scenarios that want to surface scenario-specific data on
:class:`RunDetailResponse` (per-round case ground truth, swap anchors,
judge metadata keyed by tool call_id, custom SSE events, …) ship a
``run_detail_extension`` submodule under their package. At module load
time :func:`discover_scenario_extensions` walks the
:mod:`glossogen.scenarios` namespace package, imports each
``<scenario_pkg>.run_detail_extension`` submodule when present, and
collects every :class:`ScenarioRunDetailExtension` subclass.

The platform's :mod:`glossogen.server.runs.models` builds the
``scenario_extras`` discriminated-union field on
:class:`RunDetailResponse` from the discovered extensions; the platform's
:mod:`glossogen.server.runs.detail_reader` invokes each extension's
``build_extras`` after the generic event walk.
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.scenario_submodule_discovery import concrete_subclasses, import_scenario_submodules
from glossogen.server.runs.run_detail_types import AgentDetail, ChannelMessage

logger = logging.getLogger(__name__)


class ScenarioRunExtrasBase(BaseModel):
    """Abstract base for the polymorphic payload attached to ``RunDetailResponse.scenario_extras``.

    Concrete subclasses live in each scenario's ``run_detail_extension``
    module and declare ``scenario_name: Literal["<name>"]`` as the
    discriminator field. Pydantic dispatches between subclasses on that
    field when validating the discriminated union.
    """


class ScenarioRunDetailExtension(ABC):
    """Per-scenario hook that materializes ``ScenarioRunExtrasBase`` from a run's event log.

    Subclasses live in ``glossogen.scenarios.<name>.run_detail_extension``.
    Each subclass declares the scenario it serves (``scenario_name``), the
    Pydantic class that holds its extras payload (``extras_model_cls``),
    and any custom SSE event classes the scenario emits over the live
    stream (``sse_event_classes``). Both class-vars are read at platform
    startup to build the discriminated unions on
    :class:`RunDetailResponse` and the SSE event union.
    """

    scenario_name: ClassVar[str]
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]]
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]]

    @abstractmethod
    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> ScenarioRunExtrasBase:
        """Walk ``events`` and return the scenario-specific extras payload.

        ``agents_by_id`` and ``messages`` are the already-materialized
        platform views for the same run; extensions reuse them instead
        of re-indexing the event list.
        """


def discover_scenario_extensions() -> dict[str, ScenarioRunDetailExtension]:
    """Discover every ``ScenarioRunDetailExtension`` subclass exported by a scenario.

    Walks :mod:`glossogen.scenarios`, imports each
    ``<scenario_pkg>.run_detail_extension`` submodule when present, and
    instantiates every concrete :class:`ScenarioRunDetailExtension`
    subclass it finds. Scenarios without a ``run_detail_extension``
    module are silently skipped — extensions are opt-in.
    """
    import_scenario_submodules(submodule_name="run_detail_extension")
    collected: dict[str, ScenarioRunDetailExtension] = {}
    for extension_type in concrete_subclasses(base=ScenarioRunDetailExtension):
        # concrete_subclasses drops abstract classes, so this is always instantiable;
        # pyright cannot prove the runtime concreteness of a discovered subclass.
        instance = extension_type()  # pyright: ignore[reportAbstractUsage]
        if instance.scenario_name in collected:
            raise RuntimeError(
                f"Duplicate ScenarioRunDetailExtension for scenario "
                f"{instance.scenario_name!r}: {extension_type.__qualname__}"
            )
        collected[instance.scenario_name] = instance
    return collected


SCENARIO_RUN_EXTENSIONS: dict[str, ScenarioRunDetailExtension] = (
    discover_scenario_extensions()
)
