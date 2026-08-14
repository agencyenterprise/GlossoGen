"""The version of the scenario contract this platform speaks.

A scenario in a separate distribution is written against whatever
``SimulationScenario`` looked like at the time. Adding an abstract method to that
contract already fails loudly, because the class cannot be instantiated. A hook
whose meaning changes while its signature does not will not fail at all:
``RoundWorld.on_message`` gaining a required call up to ``super()`` is that shape,
and an out-of-tree world that misses it meters nothing and reports a run that
looks complete.

The version therefore lives in the entry-point group name a plug-in declares
itself under, ``glossogen.scenarios.v1``, not in an attribute on the class. A
class attribute cannot work: an external subclass that does not set one inherits
it from the installed platform's base class, so it reports whatever version is
running and never disagrees with it. Setting it to ``SCENARIO_API_VERSION`` fails
the same way, that constant being read from the installed platform too. Only a
string the author writes into their own metadata records what they built against.

Bumping this number stops a platform reading the older group.
:func:`glossogen.scenario_entry_points.scenarios_declared_under_other_groups`
still finds those declarations, so the mismatch gets reported rather than looking
like nothing installed. Everywhere else that needs this argument points here.
"""

SCENARIO_API_VERSION = 1
