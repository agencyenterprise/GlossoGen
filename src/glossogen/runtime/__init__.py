"""Simulation runtime: the shared world that autonomous agents interact with through their tools.

Also holds the supervisor that launches the game clock and the agent runners, the event
logger that writes a run's JSONL event log, the event bus that streams those events to SSE
subscribers, the embedded server that serves that stream, and the log formatter and handler
that write debug logs to a file and publish them on the bus.
"""
