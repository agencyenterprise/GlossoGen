"""The version of the harness contract this platform speaks.

A harness in a separate distribution is written against ``AgentHarness`` and
``AgentRunner`` as they were at the time. A change to either that Python cannot
catch, such as a new event the runner is expected to log, is recorded by bumping
this number. The version lives in the entry-point group a plug-in declares itself
under, ``glossogen.agent_harnesses.v1``, for the reason given in
:mod:`glossogen.scenario_api`: only a string the author writes into their own
metadata records what they built against.
"""

HARNESS_API_VERSION = 1
