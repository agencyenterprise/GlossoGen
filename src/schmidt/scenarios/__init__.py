"""Namespace package for simulation scenarios.

Empty by design: importing ``schmidt.scenarios.<name>.events`` from
:mod:`schmidt.models.event` would otherwise eagerly load every scenario's
``scenario.py`` (which imports ``schmidt.models.event``) and create a
circular dependency. The eager registry of available scenarios lives in
:mod:`schmidt.scenario_registry` and is imported only by top-level
consumers (CLI, server, replace-agent flow).
"""
