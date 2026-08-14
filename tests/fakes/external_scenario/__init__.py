"""A scenario package standing in for one shipped by another distribution.

Laid out the way the guide tells an out-of-tree author to lay one out: a
``scenario`` module holding the class an entry point names, a sibling ``events``
module the platform discovers, and a ``knobs_*.json`` preset beside them. Nothing
here is registered in :mod:`glossogen.scenario_registry`, which is the point.

Empty for the same reason a real scenario package is: discovery imports
``<pkg>.events`` while :mod:`glossogen.models.event` is mid-import, so this must
not pull in the ``scenario`` module.
"""
