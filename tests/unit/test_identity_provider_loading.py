"""What it takes for an identity provider shipped outside glossogen to be usable.

Every ambiguity here is fatal rather than a warning, which is the one place this
loader deliberately differs from the scenario and metric loaders. The reason is the
failure mode: a scenario that fails to load leaves a feature missing and says so, but
a provider that fails to load leaves the server answering every request as the
synthetic local user, which looks exactly like a deployment that never configured
authentication. The tests below pin each refusal.
"""

from importlib.metadata import EntryPoint

import pytest

from glossogen.server.identity.identity_entry_points import IDENTITY_ENTRY_POINT_GROUP
from glossogen.server.identity.identity_provider_loader import (
    IdentityProviderNotLoadable,
    load_identity_provider,
)
from tests.fakes.identity_provider import FakeIdentityProvider
from tests.fakes.installed_entry_points import declare_in_groups

FAKE_MODULE = "tests.fakes.identity_provider"


def entry_point(name: str, attr: str) -> EntryPoint:
    """Build an entry point naming something in the fakes module."""
    return EntryPoint(name=name, value=f"{FAKE_MODULE}:{attr}", group=IDENTITY_ENTRY_POINT_GROUP)


def test_nothing_declared_is_single_tenant_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """No declaration is the zero-setup path, not an error."""
    declare_in_groups(monkeypatch=monkeypatch, groups={})
    assert load_identity_provider() is None


def test_a_declared_provider_is_loaded_and_instantiated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The entry point names a class; the loader hands back an instance."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            IDENTITY_ENTRY_POINT_GROUP: [entry_point(name="fake", attr="FakeIdentityProvider")]
        },
    )
    provider = load_identity_provider()
    assert isinstance(provider, FakeIdentityProvider)
    assert provider.provider_name() == "fake"


def test_two_declared_providers_refuse_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Choosing between two auth providers would decide how every request is checked."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            IDENTITY_ENTRY_POINT_GROUP: [
                entry_point(name="fake", attr="FakeIdentityProvider"),
                entry_point(name="also_fake", attr="GroupForbiddingProvider"),
            ]
        },
    )
    with pytest.raises(IdentityProviderNotLoadable, match="Exactly one may be installed"):
        load_identity_provider()


def test_a_provider_declared_under_an_unread_group_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A version-mismatched auth plug-in must not degrade to no authentication.

    This is the most consequential refusal in the set. Warning and carrying on, which
    is what the scenario loader does, would boot a server that authenticates nothing
    while an operator believes their provider is installed.
    """
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            "glossogen.identity_provider.v99": [
                entry_point(name="fake", attr="FakeIdentityProvider")
            ]
        },
    )
    with pytest.raises(IdentityProviderNotLoadable) as raised:
        load_identity_provider()
    message = str(raised.value)
    assert "glossogen.identity_provider.v99" in message
    assert IDENTITY_ENTRY_POINT_GROUP in message


def test_a_provider_declared_without_a_version_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping the ``.v1`` is the likeliest single mistake in a hand-typed group."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            "glossogen.identity_provider": [entry_point(name="fake", attr="FakeIdentityProvider")]
        },
    )
    with pytest.raises(IdentityProviderNotLoadable, match="glossogen.identity_provider"):
        load_identity_provider()


def test_a_declaration_under_both_groups_is_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A half-finished migration that added the new group is not an error."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            IDENTITY_ENTRY_POINT_GROUP: [entry_point(name="fake", attr="FakeIdentityProvider")],
            "glossogen.identity_provider.v99": [
                entry_point(name="fake", attr="FakeIdentityProvider")
            ],
        },
    )
    assert isinstance(load_identity_provider(), FakeIdentityProvider)


def test_an_entry_point_naming_a_non_provider_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A class that is not an IdentityProvider cannot be used as one."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={IDENTITY_ENTRY_POINT_GROUP: [entry_point(name="fake", attr="NotAProvider")]},
    )
    with pytest.raises(IdentityProviderNotLoadable, match="not an IdentityProvider subclass"):
        load_identity_provider()


def test_a_provider_that_fails_to_import_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike a metric, an auth provider that will not import is not skippable."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={IDENTITY_ENTRY_POINT_GROUP: [entry_point(name="fake", attr="NoSuchAttribute")]},
    )
    with pytest.raises(IdentityProviderNotLoadable, match="failed to import"):
        load_identity_provider()
