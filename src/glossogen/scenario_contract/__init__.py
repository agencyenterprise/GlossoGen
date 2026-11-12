"""The scenario contract: what a scenario implements and how the platform finds it.

Holds the base classes a scenario subclasses, the knobs every scenario shares,
the types a scenario implements or receives (its world and the context the
runtime gives it, its tools, notifications and wakes, the ``Metric`` contract
and the evaluation configs it declares), the runner prompts a scenario gets
unless it replaces them, the run-detail extension contract, the ``@scenario``
decorator and the per-process catalog of the scenarios it registers, the sources
a process loads scenarios from, the loader every caller resolves a scenario name
through, and the rebuild of a finished run's scenario from its recorded config.
"""
