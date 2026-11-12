"""Package holding the scenarios that ship with glossogen.

Empty by design: importing ``glossogen.scenarios.<name>.events`` from
:mod:`glossogen.models.event` would otherwise eagerly load every scenario's
``scenario.py`` (which imports ``glossogen.models.event``) and create a
circular dependency. Each scenario module registers itself with ``@scenario``,
and :mod:`glossogen.scenario_contract.catalog` imports them by scanning this
package's directory when a process loads its catalog.

A regular package, not a PEP 420 namespace one, so another distribution cannot
add a scenario by dropping a directory in here. A scenario from outside glossogen
is loaded from a configured source instead; see
:mod:`glossogen.scenario_contract.scenario_sources`.
"""
