"""The harness that drives a seat through the Claude Agent SDK.

The SDK runs the Claude Code CLI as a subprocess per seat. The seat's tools are
served to it from this process, so they execute against the live runtime exactly
as they do for a pydantic-ai seat, and the runner logs the same events from the
messages the CLI streams back.
"""
