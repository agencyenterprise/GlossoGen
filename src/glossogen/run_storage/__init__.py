"""Reading finished runs from a runs directory, with no web or database dependency.

The JSONL event log reader and the per-scenario event parsers, discovery and run
summaries, a run directory's file paths, labels file and identifier, the
derivation, eval and stream manifests, evaluation scores, copying a run at an
event, a derived run's lineage, run bundles, and the knob filter that selects
runs by their recorded config. The web server, the CLI, the runtime's swaps,
replay and the metrics all read runs through it.

A finished run's primary channels are resolved in
:mod:`glossogen.scenario_contract.primary_channel_resolution` instead, because
that rebuilds the run's scenario and this package imports no scenario code.
"""
