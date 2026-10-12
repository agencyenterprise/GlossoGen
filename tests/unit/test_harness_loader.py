"""What it takes for a harness shipped outside glossogen to drive a seat.

``entry_points`` reads installed metadata, so replacing it is the whole of what
a fake external harness needs; the classes live in ``tests/fakes/external_harness``.
"""

import logging
from importlib.metadata import EntryPoint

import pytest

from glossogen.runners.harness_entry_points import HARNESS_ENTRY_POINT_GROUP
from glossogen.runners.harness_loader import available_harness_names, get_harness_class
from glossogen.runners.harness_names import PYDANTIC_AI_HARNESS_NAME
from glossogen.runners.pydantic_ai_harness import PydanticAIHarness
from tests.fakes.external_harness import EXTERNAL_HARNESS_NAME, ExternalHarness
from tests.fakes.installed_entry_points import declare_in_groups

FAKE_MODULE = "tests.fakes.external_harness"


def entry_point(name: str, attribute: str, group: str) -> EntryPoint:
    """An entry point naming a class in the fake harness module."""
    return EntryPoint(name=name, value=f"{FAKE_MODULE}:{attribute}", group=group)


def test_the_pydantic_ai_harness_is_built_in() -> None:
    """A clone resolves the default harness with nothing installed."""
    assert get_harness_class(name=PYDANTIC_AI_HARNESS_NAME) is PydanticAIHarness


def test_an_installed_harness_is_listed_and_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """A distribution declaring a harness makes it selectable by name."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                entry_point(
                    name=EXTERNAL_HARNESS_NAME,
                    attribute="ExternalHarness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                )
            ]
        },
    )
    assert EXTERNAL_HARNESS_NAME in available_harness_names()
    assert get_harness_class(name=EXTERNAL_HARNESS_NAME) is ExternalHarness


def test_an_unknown_harness_names_what_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo is answered with the names that would have worked."""
    declare_in_groups(monkeypatch=monkeypatch, groups={})
    with pytest.raises(ValueError, match=PYDANTIC_AI_HARNESS_NAME):
        get_harness_class(name="codexx")


def test_a_harness_declared_for_another_contract_version_is_explained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A version mismatch is reported by group, not as an unknown name."""
    other_group = "glossogen.agent_harnesses.v99"
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            other_group: [
                entry_point(
                    name=EXTERNAL_HARNESS_NAME, attribute="ExternalHarness", group=other_group
                )
            ]
        },
    )
    assert EXTERNAL_HARNESS_NAME not in available_harness_names()
    with pytest.raises(ValueError, match=other_group):
        get_harness_class(name=EXTERNAL_HARNESS_NAME)


def test_an_entry_point_that_is_not_a_harness_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pointing at the wrong class fails at resolution, before a runner is asked for."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                entry_point(
                    name=EXTERNAL_HARNESS_NAME,
                    attribute="NotAHarness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                )
            ]
        },
    )
    with pytest.raises(ValueError, match="does not name an AgentHarness"):
        get_harness_class(name=EXTERNAL_HARNESS_NAME)


def test_a_harness_whose_name_disagrees_with_its_entry_point_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded harness name must be the one a later fork can resolve again."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                entry_point(
                    name="renamed", attribute="ExternalHarness", group=HARNESS_ENTRY_POINT_GROUP
                )
            ]
        },
    )
    with pytest.raises(ValueError, match="must agree"):
        get_harness_class(name="renamed")


def test_a_package_declaring_a_shipped_name_is_ignored_and_the_collision_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                entry_point(
                    name=PYDANTIC_AI_HARNESS_NAME,
                    attribute="ExternalHarness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                )
            ]
        },
    )

    with caplog.at_level(logging.WARNING, logger="glossogen.runners.harness_loader"):
        names = available_harness_names()

    assert names.count(PYDANTIC_AI_HARNESS_NAME) == 1
    assert get_harness_class(name=PYDANTIC_AI_HARNESS_NAME) is PydanticAIHarness
    assert "already provided by glossogen" in caplog.text


def test_an_entry_point_whose_module_does_not_import_is_reported_when_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                EntryPoint(
                    name=EXTERNAL_HARNESS_NAME,
                    value="tests.fakes.no_such_harness_module:Harness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                )
            ]
        },
    )

    assert EXTERNAL_HARNESS_NAME in available_harness_names(), "listing imports nothing"
    with pytest.raises(ValueError, match="failed to import"):
        get_harness_class(name=EXTERNAL_HARNESS_NAME)


def test_a_declaration_without_a_contract_version_is_reported_by_its_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bare_group = "glossogen.agent_harnesses"
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            bare_group: [
                entry_point(
                    name=EXTERNAL_HARNESS_NAME, attribute="ExternalHarness", group=bare_group
                )
            ]
        },
    )

    assert EXTERNAL_HARNESS_NAME not in available_harness_names()
    with pytest.raises(ValueError, match=f"'{bare_group}'"):
        get_harness_class(name=EXTERNAL_HARNESS_NAME)
