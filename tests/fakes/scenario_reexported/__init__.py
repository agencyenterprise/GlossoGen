"""A scenario package whose ``__init__`` re-exports the class from a submodule.

An ordinary Python idiom, and the case that separates where a class is *defined*
from where an entry point *points*. The class itself looks correct: it lives in
``scenario.py``. But an entry point naming the package is read by discovery as
naming a module inside it, so the package resolves to this one's parent and the
``events`` module looks absent.
"""

from tests.fakes.scenario_reexported.scenario import ReexportedScenario

__all__ = ["ReexportedScenario"]
