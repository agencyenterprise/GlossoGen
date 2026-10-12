"""The harness that drives a seat through the Codex CLI's app server.

``codex app-server`` speaks JSON-RPC over stdio. The seat's tools are declared
as the thread's client-defined tools, so Codex asks this process to run each
call and the tools execute against the live runtime as they do for any seat.
"""
