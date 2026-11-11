"""The scenario contract: what a scenario implements and how the platform finds it.

Holds the base classes a scenario subclasses, the run-detail extension contract,
the registry of built-in scenarios, discovery of scenarios and their event types
in other installed distributions, the loader every caller resolves a scenario
name through, and the rebuild of a finished run's scenario from its recorded
config.
"""
