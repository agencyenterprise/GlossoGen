"""Allocates ephemeral TCP ports for MCP servers and streaming servers.

Binds to port 0 on loopback to let the OS assign a free port, then
releases the socket so the caller can bind it. Used by the CLI, web
server launch paths, and the embedded streaming server.
"""

import socket


def find_free_port() -> int:
    """Find an available TCP port by briefly binding to port 0 on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port
