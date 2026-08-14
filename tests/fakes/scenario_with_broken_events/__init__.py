"""A scenario package whose ``events`` module raises on import.

Stands in for a third-party plug-in that is broken in a way discovery has to
tolerate: the platform must still read event logs that have nothing to do with it.
The same failure in a package shipped here is raised instead, because that is a bug
in this repo.
"""
