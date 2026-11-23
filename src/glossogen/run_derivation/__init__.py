"""Deriving a new run from a finished one.

The replace-agent, cross-run replace-agent and fork-at-round flows cut a finished
run at a round boundary: preparing the truncated copy, the manifests that record
where each derived run came from, and launching its resumed subprocess. The
history-transfer flow starts a fresh run, possibly of another scenario, whose
chosen seats carry the histories agents built in a finished run.
"""
