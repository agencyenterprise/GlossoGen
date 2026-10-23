"""Rebuilding agent histories and simulation state from a run's event log.

Used for resumes, forks, swaps, probes and exports: each agent's pydantic-ai
message history, the simulation state at an event, the state a resumed run
starts from, and the resume-context files that record what each resumed agent
saw.
"""
