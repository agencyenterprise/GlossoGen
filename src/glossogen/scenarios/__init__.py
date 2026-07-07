"""Namespace package for simulation scenarios.

Empty by design: importing ``glossogen.scenarios.<name>.events`` from
:mod:`glossogen.models.event` would otherwise eagerly load every scenario's
``scenario.py`` (which imports ``glossogen.models.event``) and create a
circular dependency. The eager registry of available scenarios lives in
:mod:`glossogen.scenario_registry` and is imported only by top-level
consumers (CLI, server, replace-agent flow).
"""
