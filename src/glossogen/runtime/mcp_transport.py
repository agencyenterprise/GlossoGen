"""How agents reach the MCP server: over a socket, or dispatched in-process.

A run serves the MCP app on a loopback port and every agent connects to it over
HTTP. A test mounts the same app and dispatches to it directly, so the protocol,
the tool registration and the authorization guard are exercised unchanged while
no socket exists.

The distinction is a union rather than a nullable port, so a caller states which
it wants and neither is a default.
"""

from typing import Literal, NamedTuple


class ServeOverHttp(NamedTuple):
    """Bind a loopback port and let agents connect to it."""

    port: int
    kind: Literal["http"] = "http"


class MountInProcess(NamedTuple):
    """Dispatch to the app directly, with no socket.

    ``host_url`` is what agents address the app as. It has to be a host the
    server's DNS-rebinding guard accepts, which is why it names loopback rather
    than something like ``http://mcp``: an unrecognised Host is answered with
    421 before any handler runs.
    """

    host_url: str
    kind: Literal["in_process"] = "in_process"


McpTransport = ServeOverHttp | MountInProcess

# The address an in-process app is addressed by. The port is arbitrary and
# nothing listens on it; only the host is checked.
IN_PROCESS_HOST_URL = "http://127.0.0.1:8000"
