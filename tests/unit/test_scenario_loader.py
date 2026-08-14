"""What it takes for a scenario shipped outside glossogen to be usable.

The registry of built-in scenarios is a dict in this repo, so before entry
points the only way to add a scenario was to fork. These cover the three things
an out-of-tree scenario needs and the two ways it can be wrong.

Nothing here installs a distribution. ``entry_points`` reads installed metadata,
so replacing that one function is the whole of what a fake external scenario
needs, and the fake package under ``tests/fakes/external_scenario`` is laid out
the way a real one is.
"""

import logging
from importlib.metadata import EntryPoint
from typing import Protocol

import orjson
import pytest

from glossogen import scenario_entry_points, scenario_loader
from glossogen.scenario_loader import (
    available_scenario_names,
    find_scenario_class,
    get_scenario_class,
    iter_scenario_classes,
)
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.server.runs.primary_channel_resolution import resolve_primary_channel_ids
from tests.fakes.installed_entry_points import declare_in_groups
from tests.fakes.scenario_with_bad_preset.scenario import ScenarioWithBadPreset

FAKE_PACKAGE = "tests.fakes.external_scenario"
EXTERNAL_NAME = "external_scenario"


def entry_point(name: str, attribute: str) -> EntryPoint:
    """Build an entry point naming something in the fake external package."""
    return EntryPoint(
        name=name,
        value=f"{FAKE_PACKAGE}.scenario:{attribute}",
        group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
    )


class DeclareEntryPoints(Protocol):
    """Makes the given entry points look installed for the rest of one test."""

    def __call__(self, *points: EntryPoint) -> None: ...


@pytest.fixture(autouse=True)
def forget_previous_warnings() -> None:
    """Clear the loader's once-per-process warning cache before each test.

    The cache stops a per-request listing repeating itself, which also means a
    warning fires only the first time its key is seen. Without this, a test
    asserting on a warning passes or fails on whether some earlier test happened to
    use the same scenario name.
    """
    scenario_loader.forget_reported_problems()


@pytest.fixture
def declared(monkeypatch: pytest.MonkeyPatch) -> DeclareEntryPoints:
    """Return a function that makes the given entry points look installed."""

    def declare(*points: EntryPoint) -> None:
        declare_in_groups(
            monkeypatch,
            {scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP: list(points)},
        )

    return declare


def test_a_built_in_scenario_resolves_without_any_entry_point() -> None:
    """The built-in path is unchanged by the existence of the external one."""
    assert get_scenario_class(name="veyru") is SCENARIO_REGISTRY["veyru"]


def test_the_reported_name_is_the_package_directory() -> None:
    """``name()`` and ``scenario_package_files()`` must not disagree.

    ``name()`` names the run directory and the loader checks it against the
    registered name, so a wrong answer refuses a plug-in against a directory the
    author never wrote.
    """
    for name, scenario_cls in SCENARIO_REGISTRY.items():
        assert scenario_cls.name() == name
        assert scenario_cls.name() == scenario_cls.scenario_package_files().name


def test_a_class_defined_in_a_package_init_is_refused(declared: DeclareEntryPoints) -> None:
    """That layout cannot be discovered, so it is refused rather than half-run.

    Finding the package an entry point names is a string operation, because it
    happens while ``glossogen.models.event`` is mid-import and may not import
    anything. Telling a package from a module needs an import, so a class in a
    package's ``__init__`` would be misread as living in its parent, the
    ``events`` module would look absent, and the scenario's event types would be
    missing from the parser. The run would write fine and its JSONL would not
    parse back.
    """
    in_init_package = "tests.fakes.scenario_in_package_init"
    declared(
        EntryPoint(
            name="scenario_in_package_init",
            value=f"{in_init_package}:ScenarioInPackageInit",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        )
    )

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name="scenario_in_package_init")

    message = str(caught.value)
    assert "__init__" in message
    assert f"{in_init_package}.scenario:ScenarioInPackageInit" in message, "where to move it"


def test_an_external_scenario_resolves_by_name(declared: DeclareEntryPoints) -> None:
    """The whole point: a class this repo does not import, found by name."""
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))

    resolved = get_scenario_class(name=EXTERNAL_NAME)

    assert resolved.__module__ == f"{FAKE_PACKAGE}.scenario"
    assert resolved.__name__ == "ExternalScenario"


def test_an_external_scenario_is_listed_among_the_available_names(
    declared: DeclareEntryPoints,
) -> None:
    """Listing must not miss it, or the CLI would reject a name it can run."""
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))

    names = available_scenario_names()

    assert EXTERNAL_NAME in names
    assert set(SCENARIO_REGISTRY) <= set(names), "a built-in went missing"


def test_an_external_scenario_serves_its_own_presets(declared: DeclareEntryPoints) -> None:
    """Presets come from the scenario's own package, not a path under glossogen."""
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))
    resolved = get_scenario_class(name=EXTERNAL_NAME)

    assert resolved.knobs_preset_names() == ["knobs_external_default"]
    preset = resolved.load_knobs_preset(preset_name="knobs_external_default")
    assert preset["round_count"] == 2
    assert preset["seed"] == 42


def test_a_built_in_wins_a_name_collision(declared: DeclareEntryPoints) -> None:
    """An installed package must not be able to redefine what `veyru` means.

    A run's config records only the scenario name, so letting a third party take
    an existing name would make an old run irreproducible.
    """
    declared(entry_point(name="veyru", attribute="ExternalScenario"))

    assert get_scenario_class(name="veyru") is SCENARIO_REGISTRY["veyru"]


def test_a_scenario_declared_for_another_contract_version_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plug-in built against another contract says so in its group name.

    The version cannot be a class attribute: an external subclass that does not
    set one inherits it from the installed platform's base class, so it always
    reports the running version and never disagrees with it. Putting it in the
    group means a platform that has moved on does not read that group at all, and
    the job here is to say so rather than let the scenario look uninstalled.
    """
    other_group = f"{scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP_PREFIX}99"
    declare_in_groups(
        monkeypatch,
        {
            other_group: [
                EntryPoint(
                    name=EXTERNAL_NAME,
                    value=f"{FAKE_PACKAGE}.scenario:ExternalScenario",
                    group=other_group,
                )
            ]
        },
    )

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name=EXTERNAL_NAME)

    message = str(caught.value)
    assert other_group in message, "the group the plug-in used"
    assert scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP in message, "the group read"


def test_a_scenario_declared_for_this_version_is_not_reported_as_skewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current group must not be mistaken for a mismatched one."""
    declare_in_groups(
        monkeypatch,
        {
            scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP: [
                entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario")
            ]
        },
    )

    assert scenario_entry_points.scenarios_declared_under_other_groups() == {}
    assert get_scenario_class(name=EXTERNAL_NAME).name() == EXTERNAL_NAME


def test_the_listing_says_why_a_skewed_plug_in_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Listing is the first place an operator looks after installing a plug-in.

    Without this the scenario is absent from the CLI list, `GET /scenarios` and
    the MCP tool with nothing said, which is the indistinguishable absence the
    group mechanism exists to avoid. Only guessing the name and asking for it
    directly would explain anything.
    """
    other_group = f"{scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP_PREFIX}99"
    declare_in_groups(
        monkeypatch,
        {
            other_group: [
                EntryPoint(
                    name="skewed",
                    value=f"{FAKE_PACKAGE}.scenario:ExternalScenario",
                    group=other_group,
                )
            ]
        },
    )

    with caplog.at_level(logging.WARNING):
        names = available_scenario_names()
        listed = dict(iter_scenario_classes())

    assert "skewed" not in names
    assert "skewed" not in listed
    assert "skewed" in caplog.text
    assert other_group in caplog.text


def test_the_unversioned_group_is_treated_as_a_mistake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping the ``.v1`` is the likeliest single typo, and reads as nothing.

    The group name is the one thing a plug-in author types by hand, so the bare
    prefix gets the same explanation a version difference does.
    """
    bare_group = "glossogen.scenarios"
    declare_in_groups(
        monkeypatch,
        {
            bare_group: [
                EntryPoint(
                    name="typoed",
                    value=f"{FAKE_PACKAGE}.scenario:ExternalScenario",
                    group=bare_group,
                )
            ]
        },
    )

    assert scenario_entry_points.scenarios_declared_under_other_groups() == {"typoed": bare_group}
    with pytest.raises(ValueError, match=bare_group):
        get_scenario_class(name="typoed")


def test_an_entry_point_naming_the_wrong_object_is_refused(declared: DeclareEntryPoints) -> None:
    """Pointing at something that is not a scenario names the entry point."""
    declared(entry_point(name=EXTERNAL_NAME, attribute="NOT_A_SCENARIO"))

    with pytest.raises(ValueError, match=EXTERNAL_NAME):
        get_scenario_class(name=EXTERNAL_NAME)


def test_a_scenario_that_calls_itself_something_else_is_refused(
    declared: DeclareEntryPoints,
) -> None:
    """The registered name and ``name()`` have to agree, or a run goes missing.

    Run directories are named after ``name()``, while `glossogen run`, `evaluate`
    and the resume flows look a run up by the name it was launched with. A
    disagreement puts the run somewhere none of them will find it, and nothing
    about the run looks wrong while it happens.
    """
    declared(entry_point(name=EXTERNAL_NAME, attribute="RenamedScenario"))

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name=EXTERNAL_NAME)

    message = str(caught.value)
    assert EXTERNAL_NAME in message
    assert "some_other_name" in message


def test_a_matching_name_is_accepted(declared: DeclareEntryPoints) -> None:
    """The check passes when the two agree, which is the ordinary case.

    ``ExternalScenario`` lives in ``tests.fakes.external_scenario.scenario``, so
    the name it derives is ``external_scenario``.
    """
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))

    assert get_scenario_class(name=EXTERNAL_NAME).name() == EXTERNAL_NAME


def test_an_entry_point_whose_module_raises_is_refused_with_context(
    declared: DeclareEntryPoints,
) -> None:
    """A bad import inside the plug-in must not surface as a bare ImportError.

    The caller asked for this scenario by name, so there is nothing to fall back
    to; what matters is that the error says which entry point is at fault.
    """
    declared(
        EntryPoint(
            name=EXTERNAL_NAME,
            value="tests.fakes.no_such_module:BrokenImportScenario",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        )
    )

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name=EXTERNAL_NAME)

    assert "tests.fakes.no_such_module" in str(caught.value)


def test_one_unusable_external_scenario_does_not_take_down_the_listing(
    declared: DeclareEntryPoints,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The listing backs `GET /scenarios` and the MCP `list_scenarios` tool.

    Raising here would let one third-party plug-in hide every scenario shipped
    here, leaving no way to run any of them. Asking for the broken one by name
    still raises, which the test below pins.
    """
    declared(entry_point(name="misdeclared", attribute="RenamedScenario"))

    with caplog.at_level(logging.ERROR):
        listed = dict(iter_scenario_classes())

    assert "misdeclared" not in listed
    assert set(SCENARIO_REGISTRY) <= set(listed), "a built-in was lost with the broken one"
    assert "misdeclared" in caplog.text


def test_asking_for_the_broken_one_by_name_still_raises(declared: DeclareEntryPoints) -> None:
    """Tolerance belongs to listing, not to a lookup the caller asked for."""
    declared(entry_point(name="misdeclared", attribute="RenamedScenario"))

    with pytest.raises(ValueError):
        get_scenario_class(name="misdeclared")


def test_a_shadowed_external_scenario_is_reported(
    declared: DeclareEntryPoints,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The built-in wins, and the author of the shadowed one is told why.

    Without this the symptom is a name that quietly resolves to somebody else's
    scenario.
    """
    declared(entry_point(name="veyru", attribute="ExternalScenario"))

    with caplog.at_level(logging.WARNING):
        available_scenario_names()

    assert "veyru" in caplog.text
    assert "already provided by glossogen" in caplog.text


def test_an_unknown_name_is_not_an_error_for_find(declared: DeclareEntryPoints) -> None:
    """A run whose scenario is no longer installed is an ordinary outcome."""
    declared()

    assert find_scenario_class(name="no_such_scenario") is None


def test_an_unknown_name_lists_what_is_available(declared: DeclareEntryPoints) -> None:
    """The error is the only place a caller learns what it could have asked for."""
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name="no_such_scenario")

    assert EXTERNAL_NAME in str(caught.value)
    assert "veyru" in str(caught.value)


def test_two_distributions_claiming_one_name_keep_the_first(declared: DeclareEntryPoints) -> None:
    """Ambiguity resolved silently would make a run unreproducible."""
    declared(
        entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"),
        entry_point(name=EXTERNAL_NAME, attribute="SecondExternalScenario"),
    )

    resolved = get_scenario_class(name=EXTERNAL_NAME)

    assert resolved.__name__ == "ExternalScenario"


def test_an_external_scenario_builds_and_renders_from_its_own_package(
    declared: DeclareEntryPoints,
) -> None:
    """Resolving a scenario is not the same as it working.

    Builds it the way the CLI does, from its own preset, and checks the agent's
    prompt came from a template inside the scenario's package. That last part is
    what the guide promises and what a path computed under ``glossogen`` would
    break.
    """
    declared(entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario"))
    scenario_cls = get_scenario_class(name=EXTERNAL_NAME)

    config = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_external_default"))
    )
    scenario = scenario_cls.create_from_config(config=config)
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")

    assert [channel.channel_id for channel in scenario.get_channels()] == ["link"]
    assert len(agents) == 1
    assert "the link" in agents[0].system_prompt, "prompt rendered from the scenario's package"
    assert scenario.judge_round_result(round_number=1, trigger="round_timeout")[0].success


def test_an_entry_point_naming_a_re_exporting_package_is_refused(
    declared: DeclareEntryPoints,
) -> None:
    """The class looks fine; the entry point does not.

    A package ``__init__`` that re-exports its class is ordinary packaging, and it
    separates where the class is defined from where the entry point points.
    Checking the class would pass: it lives in a submodule with no ``__path__``.
    Discovery reads the package from the entry-point string, so it is that string
    which has to name a module.
    """
    package = "tests.fakes.scenario_reexported"
    declared(
        EntryPoint(
            name="scenario_reexported",
            value=f"{package}:ReexportedScenario",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        )
    )

    with pytest.raises(ValueError) as caught:
        get_scenario_class(name="scenario_reexported")

    message = str(caught.value)
    assert f"'{package}' package" in message
    assert f"{package}.scenario:ReexportedScenario" in message, "names the module to point at"


def test_a_name_declared_under_both_groups_is_usable_and_not_warned_about(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """What a half-finished migration looks like: new group added, old one still there.

    The scenario is readable, so there is nothing to report. Warning here would
    point someone at a non-problem exactly when they had just done the migration
    correctly, and the warning's own text would be false.
    """
    current = scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP
    stale = "glossogen.scenarios"
    declare_in_groups(
        monkeypatch,
        {
            current: [entry_point(name=EXTERNAL_NAME, attribute="ExternalScenario")],
            stale: [
                EntryPoint(
                    name=EXTERNAL_NAME,
                    value=f"{FAKE_PACKAGE}.scenario:ExternalScenario",
                    group=stale,
                )
            ],
        },
    )

    with caplog.at_level(logging.WARNING):
        listed = dict(iter_scenario_classes())

    assert EXTERNAL_NAME in listed, "declared under the readable group, so it is usable"
    assert scenario_entry_points.scenarios_declared_under_other_groups() == {}
    assert "Not listing it" not in caplog.text


def test_a_broken_plug_in_answers_none_rather_than_raising(
    declared: DeclareEntryPoints,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The contract the tolerant server callers rest on.

    ``resolve_primary_channel_ids``, the evaluate endpoint and the knobs endpoint
    all handle None and none of them catch. A raise here turns a degraded
    run-detail page, a 422 and a 404 into three 500s, on the one path the design
    otherwise keeps serving.
    """
    declared(entry_point(name="misdeclared", attribute="RenamedScenario"))

    with caplog.at_level(logging.ERROR):
        assert find_scenario_class(name="misdeclared") is None

    assert "misdeclared" in caplog.text, "answered None, but said why"


def test_every_way_a_plug_in_can_be_broken_answers_none(
    declared: DeclareEntryPoints,
) -> None:
    """All four refusals reach the tolerant callers the same way."""
    package_pointing = EntryPoint(
        name="broken",
        value="tests.fakes.scenario_reexported:ReexportedScenario",
        group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
    )
    bad_import = EntryPoint(
        name="broken",
        value="tests.fakes.no_such_module:Whatever",
        group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
    )
    for declaration in (
        entry_point(name="broken", attribute="RenamedScenario"),
        entry_point(name="broken", attribute="NOT_A_SCENARIO"),
        package_pointing,
        bad_import,
    ):
        declared(declaration)
        assert find_scenario_class(name="broken") is None, declaration.value


def test_asking_by_name_still_explains_the_breakage(declared: DeclareEntryPoints) -> None:
    """The soft path must not cost the hard path its message."""
    declared(entry_point(name="misdeclared", attribute="RenamedScenario"))

    with pytest.raises(ValueError, match="some_other_name"):
        get_scenario_class(name="misdeclared")


def test_a_tolerant_caller_degrades_instead_of_failing(declared: DeclareEntryPoints) -> None:
    """End to end through the function the run-detail endpoint actually calls."""
    declared(entry_point(name="misdeclared", attribute="RenamedScenario"))

    assert resolve_primary_channel_ids(scenario_name="misdeclared", scenario_config={}) == []


def test_a_preset_that_does_not_parse_is_not_reported_as_missing() -> None:
    """The two failures are different questions and must not read the same.

    ``load_knobs_preset`` raises ValueError for a preset it does not ship, and
    orjson raises a ValueError subclass for one it cannot parse. A caller that
    cannot tell them apart says "not found" about a file sitting right there.
    """
    assert ScenarioWithBadPreset.knobs_preset_names() == ["knobs_broken"], "it does ship it"
    with pytest.raises(orjson.JSONDecodeError):
        ScenarioWithBadPreset.load_knobs_preset(preset_name="knobs_broken")
    with pytest.raises(ValueError, match="not found"):
        ScenarioWithBadPreset.load_knobs_preset(preset_name="knobs_absent")
