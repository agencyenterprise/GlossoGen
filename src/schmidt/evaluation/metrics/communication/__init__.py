"""Scenario-agnostic communication-feature analysis pipeline.

Two-pass + consolidate flow: open coding labels each run's per-round
ground truth + primary-channel transcript with free-form mechanism
labels (pass 1); a consolidation script merges those labels into a
shared ontology; the feature-presence metric rescores each run against
the ontology and writes a per-run vector sidecar (pass 3). All three
phases read ``CommunicationRoundView`` objects produced by each
scenario's ``build_communication_rounds`` hook, so the pipeline is
scenario-agnostic and the prompts never reference scenario-specific
domain vocabulary.

This ``__init__`` is intentionally empty to avoid a circular import:
``scenario_protocol`` imports ``CommunicationRoundView`` from the
``round_view`` submodule, and ``metric_protocol`` imports
``SimulationScenario`` from ``scenario_protocol``. Importing the
metric classes here would close the cycle. Callers import directly
from the submodule (``...communication.round_view``,
``...communication.communication_open_coding_metric``).
"""
