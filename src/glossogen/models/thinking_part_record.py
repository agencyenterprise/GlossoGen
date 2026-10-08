"""One thinking part of a model response, as recorded in the event log."""

from pydantic import BaseModel


class ThinkingPartRecord(BaseModel):
    """A thinking part with what its provider needs to accept it back.

    ``id`` and ``signature`` are the provider's own identifiers for the part:
    OpenAI's reasoning item id and encrypted content, Anthropic's block
    signature. ``provider_name`` names the provider that issued them. A
    reconstructed history rebuilds the part from these three fields, so the
    provider receives it in the form a live run sends.
    """

    content: str
    id: str | None
    signature: str | None
    provider_name: str | None
