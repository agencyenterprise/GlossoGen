"""Package holding the scenarios that ship with glossogen.

Empty by design: importing ``glossogen.scenarios.<name>.events`` from
:mod:`glossogen.models.event` would otherwise eagerly load every scenario's
``scenario.py`` (which imports ``glossogen.models.event``) and create a
circular dependency. The eager registry of the scenarios shipped here lives in
:mod:`glossogen.scenario_registry` and is imported only by top-level
consumers (CLI, server, replace-agent flow).

A regular package, not a PEP 420 namespace one, so another distribution cannot
add a scenario by dropping a directory in here. It contributes one by declaring
a ``glossogen.scenarios.v<N>`` entry point instead; see
:mod:`glossogen.scenario_entry_points`.
"""
