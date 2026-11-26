"""Which adapters the policy server keeps loaded, and the requests that change them.

The loop writes an ``AdapterRequest`` into the app's control Dict. The policy server's loader
thread hands it to ``LoadedAdapters.handle``, which asks vLLM to load the requested adapter and
then unloads each loaded adapter that the request does not list in ``keep``. A game that plays
an adapter therefore keeps it loaded for as long as the loop lists it in ``keep``. The loader
writes the ``AdapterResult`` back into the Dict.

This module imports nothing outside the standard library: it runs in the policy server's image,
and the loop's tests run it on CPU.
"""

import logging
from typing import NamedTuple, Protocol

logger = logging.getLogger(__name__)

ADAPTER_REQUEST_KEY = "adapter_request"
ADAPTER_RESULT_KEY = "adapter_result"
LOAD_PATH = "/v1/load_lora_adapter"
UNLOAD_PATH = "/v1/unload_lora_adapter"
ALREADY_LOADED = "has already been loaded"


class AdapterRequest(NamedTuple):
    """Load the adapter at ``path`` under ``name``, then unload every adapter not in ``keep``."""

    id: str
    name: str
    path: str
    keep: tuple[str, ...]


class AdapterResult(NamedTuple):
    """The outcome of one ``AdapterRequest``: whether the adapter is loaded, vLLM's answer to
    the load, and the adapters that the request unloaded."""

    id: str
    loaded: bool
    status: int
    body: str
    unloaded: tuple[str, ...]


class VllmReply(NamedTuple):
    """vLLM's HTTP status and response text for one request."""

    status: int
    body: str


class PostToVllm(Protocol):
    """POSTs a JSON body to a path of the local vLLM server."""

    def __call__(self, *, path: str, body: dict[str, str]) -> VllmReply: ...


class LoadedAdapters:
    """The adapters that this loader has loaded into vLLM and not unloaded."""

    def __init__(self, post: PostToVllm) -> None:
        self._post = post
        self.names: set[str] = set()

    def handle(self, request: AdapterRequest) -> AdapterResult:
        """Load the request's adapter; once it is loaded, unload the ones that ``keep`` leaves
        out."""
        reply = self._post(
            path=LOAD_PATH, body={"lora_name": request.name, "lora_path": request.path}
        )
        loaded = reply.status == 200 or (reply.status == 400 and ALREADY_LOADED in reply.body)
        unloaded: tuple[str, ...] = ()
        if loaded:
            self.names.add(request.name)
            unloaded = self._unload_all_but(keep={*request.keep, request.name})
        return AdapterResult(
            id=request.id,
            loaded=loaded,
            status=reply.status,
            body=reply.body[:2000],
            unloaded=unloaded,
        )

    def _unload_all_but(self, *, keep: set[str]) -> tuple[str, ...]:
        """Unload each loaded adapter that is not in ``keep``; return the ones vLLM unloaded."""
        unloaded: list[str] = []
        for name in sorted(self.names - keep):
            reply = self._post(path=UNLOAD_PATH, body={"lora_name": name})
            if reply.status == 200:
                self.names.discard(name)
                unloaded.append(name)
            else:
                logger.error("unloading %s failed: %s %s", name, reply.status, reply.body[:300])
        return tuple(unloaded)
