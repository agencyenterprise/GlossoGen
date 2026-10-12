"""The runner shared by harnesses that run a seat inside another agent CLI's loop.

A harness of this kind provides a ``SeatSession`` over its CLI; ``SessionSeatRunner``
turns what the session reports into the platform's events and serves the seat's
tools through the same executors a pydantic-ai seat uses.
"""
