"""The contract an identity provider implements.

The platform ships no provider. It routes by group slug, owns the ``groups`` table,
and attaches an :class:`~glossogen.server.identity.identity_model.Identity` to every
request, but it does not know how a caller proves who they are. A deployment that
needs authentication installs a distribution declaring one provider under
``glossogen.identity_provider.v1``.

No provider installed is single-tenant mode: every request resolves to the synthetic
``local`` group. That is why the platform needs no built-in implementation of this
contract, and why nothing here is optional to implement.

This file is one half of the seam: what a provider gives the platform. The other
half, what the platform offers a provider, is
:mod:`glossogen.server.identity.provider_services`. A provider needs both.
"""

from abc import ABC, abstractmethod

from fastapi import APIRouter

from glossogen.db.rows import GroupRow
from glossogen.server.identity.identity_model import Identity


class IdentityRejected(Exception):
    """A credential does not authorize the request it arrived on.

    Carries the HTTP status the middleware answers with: 401 for a credential that
    does not verify, 403 for one that verifies but does not cover the group named in
    the URL. Distinguishing them matters to a client, which can refresh a token in
    the first case and cannot in the second.

    The choice is presentational only. Whichever status is raised, the middleware
    still tries the credential as an MCP OAuth access token before answering, so a
    provider cannot accidentally cut off the CLI's REST access by rejecting an MCP
    token with the status it considers more accurate.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class IdentityProvider(ABC):
    """Verifies credentials and contributes the endpoints its flow needs."""

    @abstractmethod
    def provider_name(self) -> str:
        """Short name for this provider, reported in startup logs."""

    @abstractmethod
    def unauthenticated_path_prefixes(self) -> tuple[str, ...]:
        """Path prefixes this provider serves without an Identity.

        A provider's own webhook and callback endpoints are called by its identity
        service rather than by a signed-in user, so they cannot carry a group slug or
        a session credential. Every prefix returned here bypasses identity
        resolution entirely, so it should cover exactly the paths
        :meth:`routers` adds and nothing wider.
        """

    @abstractmethod
    def routers(self) -> tuple[APIRouter, ...]:
        """Routers this provider contributes to the application."""

    @abstractmethod
    def deferred_consent_url(self, request_id: str) -> str:
        """Where to send a user-agent that must choose a group before a token is minted.

        The MCP OAuth flow parks an authorization request and redirects here. The
        page this points at signs the user in, resolves which group they are
        authorizing, and posts back to an endpoint from :meth:`routers`, which
        finishes the flow by calling
        :func:`~glossogen.server.identity.provider_services.approve_parked_consent`.

        Build the URL from
        :func:`~glossogen.server.identity.provider_services.frontend_base_url` rather
        than reading the environment, so the fallback order stays in one place.
        """

    @abstractmethod
    async def resolve_identity(self, credential: str, group: GroupRow) -> Identity:
        """Verify ``credential`` and return the Identity it grants for ``group``.

        One method answers three questions, because one verification settles all
        three: whether the credential is valid, whether it authorizes *this* group,
        and whose it is. Raise :class:`IdentityRejected` for any negative answer.

        Called only after the platform has extracted a non-empty credential and
        resolved the URL's ``/g/{slug}/`` to a ``groups`` row, so a provider never
        repeats the missing-credential, missing-slug, or unknown-slug checks, and
        never queries the ``groups`` table itself.

        The credential will not always be one this provider issued. The CLI presents
        MCP OAuth access tokens to the same routes, so rejecting anything
        unrecognised is correct: the middleware tries that interpretation itself
        afterwards.
        """
