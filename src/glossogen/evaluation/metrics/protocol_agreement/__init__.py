"""The ``protocol_agreement`` metric: how the agents came to share each convention.

An LLM judge reads every message and tool call of the run, each labelled with a short
reference, and names the conventions the agents used, the agent and messages that first
used each one, and the messages in which another agent showed that it understood it.
The metric keeps only references that exist in the run, attaches the logged text of
each, and writes the result to a sidecar that the run page shows.
"""
