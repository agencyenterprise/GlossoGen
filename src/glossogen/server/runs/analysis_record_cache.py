"""Holding a selection's loaded runs for a short while.

Building a chart is a conversation: change the grouping, add a measure, flip an
aggregate. Each of those is one query, and each would otherwise re-read one evaluation
report per selected run. On a few hundred runs that is the whole cost of the request,
repeated for a change that touched no run at all.

The budget is counted in runs, not in entries, because that is what the memory is. An
entry count would bound sixteen cohorts of any width, which bounds nothing. What is
held is the projected record, an order of magnitude smaller than the full report it
came from, which is what lets a scenario-wide cohort fit. A selection larger than the
whole budget is loaded and not kept, so a very wide cohort is slow to edit rather than
fatal to hold.

Entries expire quickly, because a run that has just been evaluated should appear
without anyone restarting a server.

Concurrent requests for one selection share a single load. React Query already
deduplicates on the client, but a shared dashboard opened by two people at once does
not go through one client.

Time is a parameter rather than something read here, so a test states what "later"
means instead of waiting for it.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import NamedTuple

from glossogen.run_analysis.analysis_run_record import AnalysisRunRecord

RECORD_CACHE_TTL_SECONDS = 60.0

# Enough for the widest single scenario a study has, with room for a second cohort
# beside it. At the projected record's size this is a low hundreds of megabytes.
RECORD_CACHE_MAX_RUNS = 6_000


class CacheEntry(NamedTuple):
    """One selection's in-flight or completed load, its size, and when it goes stale."""

    expires_at: float
    run_count: int
    task: asyncio.Task[list[AnalysisRunRecord]]


class AnalysisRecordCache:
    """A time- and size-bounded cache of loaded run records, keyed by selection."""

    def __init__(self, ttl_seconds: float, max_runs: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_runs = max_runs
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def cached_run_count(self) -> int:
        """Return how many runs are currently held across every entry."""
        return sum(entry.run_count for entry in self._entries.values())

    def _drop_expired(self, now: float) -> None:
        """Remove entries whose window has passed."""
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    def _make_room(self, run_count: int) -> None:
        """Evict least recently used entries until this many more runs fit."""
        while self._entries and self.cached_run_count() + run_count > self._max_runs:
            self._entries.popitem(last=False)

    async def records(
        self,
        key: str,
        now: float,
        run_count: int,
        load: Callable[[], Awaitable[list[AnalysisRunRecord]]],
    ) -> list[AnalysisRunRecord]:
        """Return the selection's records, loading them only when none are held."""
        self._drop_expired(now=now)
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
            # Shielded, because a client that disconnects mid-request would
            # otherwise cancel the shared load out from under everyone waiting on it.
            return await asyncio.shield(entry.task)

        if run_count > self._max_runs:
            return await load()

        self._make_room(run_count=run_count)
        task = asyncio.ensure_future(load())
        entry = CacheEntry(expires_at=now + self._ttl_seconds, run_count=run_count, task=task)
        self._entries[key] = entry
        try:
            return await asyncio.shield(task)
        except Exception:
            # Only this entry. A later request for the same selection may already have
            # replaced it after expiry, and dropping whatever now sits at the key would
            # throw away a healthy in-flight load.
            if self._entries.get(key) is entry:
                self._entries.pop(key, None)
            raise
