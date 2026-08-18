"""An identity provider standing in for a real one.

The platform ships no provider, so exercising the seam needs one from somewhere. The
verdict is configurable per instance, which is what lets a test drive the rejection
paths without holding a credential anything would actually verify.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from glossogen.db.rows import GroupRow
from glossogen.server.identity.identity_model import Identity
from glossogen.server.identity.identity_provider import IdentityProvider, IdentityRejected

FAKE_WEBHOOK_PATH = "/api/fake-provider/webhook"
FAKE_USER_ID = "fake-user"

router = APIRouter()


class FakeWebhookResponse(BaseModel):
    """Response for the fake provider's webhook."""

    received: bool


@router.post(FAKE_WEBHOOK_PATH, response_model=FakeWebhookResponse)
async def fake_webhook() -> FakeWebhookResponse:
    """Stand in for a provider endpoint its identity service calls."""
    return FakeWebhookResponse(received=True)


class FakeIdentityProvider(IdentityProvider):
    """Accepts one credential value and rejects everything else."""

    accepted_credential = "good-token"

    def provider_name(self) -> str:
        """Return the provider's short name."""
        return "fake"

    def unauthenticated_path_prefixes(self) -> tuple[str, ...]:
        """Return the prefix covering this provider's own webhook."""
        return (FAKE_WEBHOOK_PATH,)

    def routers(self) -> tuple[APIRouter, ...]:
        """Return the provider's contributed router."""
        return (router,)

    def deferred_consent_url(self, request_id: str) -> str:
        """Return a consent page URL carrying the parked request id."""
        return f"https://fake-provider.test/consent?request_id={request_id}"

    async def resolve_identity(self, credential: str, group: GroupRow) -> Identity:
        """Accept ``accepted_credential`` for any group; reject anything else."""
        if credential != self.accepted_credential:
            raise IdentityRejected(status_code=401, detail="Fake credential not recognised")
        return Identity(user_id=FAKE_USER_ID, active_group_id=group.id, is_local_mode=False)


class GroupForbiddingProvider(FakeIdentityProvider):
    """Verifies the credential but denies the group, which is the 403 path."""

    async def resolve_identity(
        self,
        credential: str,  # noqa: ARG002 — contract-required
        group: GroupRow,
    ) -> Identity:
        """Always reject with 403, as a provider does for a non-member."""
        raise IdentityRejected(status_code=403, detail=f"Not a member of {group.slug!r}")


class NotAProvider:
    """Named by an entry point that should be refused for not being a provider."""
