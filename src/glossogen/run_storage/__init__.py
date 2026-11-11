"""Reading finished runs from a runs directory, with no web or database dependency.

The JSONL event log reader, discovery and run summaries, derivation manifests,
evaluation scores, primary channel resolution, and run bundles. The web server,
the CLI, the runtime's swaps, replay and the metrics all read runs through it.
"""
