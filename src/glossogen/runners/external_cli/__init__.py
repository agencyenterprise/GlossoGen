"""Harnesses that run a seat in an agent CLI connected to the run over MCP.

The run serves each such seat's tools from its own process on a loopback MCP
endpoint, and the CLI (Claude Code or Codex) is started as an ordinary
subprocess pointed at that endpoint. The CLI drives its own model loop; the
platform sees the seat's tool calls, which it logs, and the turn's usage, which
the CLI reports when it exits.
"""
