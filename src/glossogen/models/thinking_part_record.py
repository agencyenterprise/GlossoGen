"""One thinking part of a model response, as recorded in the event log."""

from typing import Any

from pydantic import BaseModel


class ThinkingPartRecord(BaseModel):
    """A thinking part with what its provider needs to accept it back.

    The identifiers and provider details are copied back into reconstructed
    history so the provider receives the same state as in a live run.
    """

    content: str
    id: str | None
    signature: str | None
    provider_name: str | None
    provider_details: dict[str, Any] | None = None
