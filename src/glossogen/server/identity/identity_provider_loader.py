"""Resolving the installed identity provider, if there is one.

Returns ``None`` when nothing is declared, which is single-tenant mode. Every other
unexpected situation raises rather than falling back to ``None``.

That is the one place this loader deliberately differs from
:mod:`glossogen.scenario_loader` and :mod:`glossogen.evaluation.metric_core.metric_registry`,
which warn and carry on. For a scenario or a metric, an unreadable declaration means
a missing feature. For an identity provider it means the server boots performing no
authentication while an operator believes it is protected, so every ambiguity is
fatal instead.
"""

import logging
from importlib.metadata import EntryPoint

from glossogen.server.identity.identity_entry_points import (
    IDENTITY_ENTRY_POINT_GROUP,
    identity_provider_declarations,
)
from glossogen.server.identity.identity_provider import IdentityProvider

logger = logging.getLogger(__name__)


class IdentityProviderNotLoadable(Exception):
    """An identity provider is declared but cannot be used as declared."""


def load_identity_provider() -> IdentityProvider | None:
    """Instantiate the declared identity provider, or return ``None`` if none is.

    Raises :class:`IdentityProviderNotLoadable` when a declaration exists but cannot
    be honoured: more than one provider, a declaration under a group this platform
    does not read, an entry point that fails to import, or one naming something that
    is not an :class:`IdentityProvider` subclass.
    """
    declarations = identity_provider_declarations()

    if declarations.other_groups:
        described = ", ".join(
            f"{name!r} under {group!r}" for name, group in sorted(declarations.other_groups.items())
        )
        raise IdentityProviderNotLoadable(
            f"Identity provider declared under a group this platform does not read: "
            f"{described}. This platform reads {IDENTITY_ENTRY_POINT_GROUP!r}. "
            "Refusing to start: continuing would run with no authentication at all, "
            "which looks identical to a deployment that never configured one."
        )

    if not declarations.current:
        logger.info("No identity provider installed; running in single-tenant mode")
        return None

    if len(declarations.current) > 1:
        names = ", ".join(sorted(declarations.current))
        raise IdentityProviderNotLoadable(
            f"{len(declarations.current)} identity providers are declared in "
            f"{IDENTITY_ENTRY_POINT_GROUP!r} ({names}). Exactly one may be installed: "
            "choosing between them would decide how every request is authenticated."
        )

    name, entry_point = next(iter(declarations.current.items()))
    return _instantiate(name=name, entry_point=entry_point)


def _instantiate(name: str, entry_point: EntryPoint) -> IdentityProvider:
    """Import what an entry point names, check it is a provider class, and build one."""
    try:
        loaded: object = entry_point.load()
    except Exception as exc:
        logger.exception("Identity provider entry point failed to import")
        raise IdentityProviderNotLoadable(
            f"Identity provider {name!r} ({entry_point.value}) failed to import: {exc}"
        ) from exc
    if not isinstance(loaded, type) or not issubclass(loaded, IdentityProvider):
        raise IdentityProviderNotLoadable(
            f"Identity provider {name!r} ({entry_point.value}) is not an "
            f"IdentityProvider subclass"
        )
    provider = loaded()
    logger.info("Identity provider loaded: %s (%s)", provider.provider_name(), entry_point.value)
    return provider
