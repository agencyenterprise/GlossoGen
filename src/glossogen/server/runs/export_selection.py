"""Resolving an export selection against the runs the active group owns.

Both branches end in the same pure resolver, so ordering and de-duplication are
identical however the candidates were found. What differs is only how wide a net
is cast:

* A filter selection asks the listing for exactly what those filters match, so
  the database narrows by scenario before any run directory is read.
* An explicit selection has to enumerate the group's runs to know which of the
  requested ids it owns. That is the price of answering "is this id mine" without
  trusting the caller, and it is why the export preview reports the ids it could
  not resolve, instead of the endpoint failing on the first one.

Group scoping is not re-implemented here. Both listing helpers already resolve the
active group from the request's identity, so a run another group owns is never a
candidate.
"""

import logging

from fastapi import Request

from glossogen.run_export.export_request_models import ExplicitRunSelection, RunSelection
from glossogen.run_export.run_selection_resolution import ResolvedSelection, resolve_selection
from glossogen.server.runs.listing import (
    list_runs_for_group,
    list_runs_matching_filters_for_group,
)

logger = logging.getLogger(__name__)


async def resolve_export_selection(
    request: Request,
    selection: RunSelection,
) -> ResolvedSelection:
    """Return the runs ``selection`` names within the active group."""
    if isinstance(selection, ExplicitRunSelection):
        candidates = await list_runs_for_group(request=request, scenario_filter=None)
        return resolve_selection(candidates=candidates, selection=selection)

    logger.info(
        "Resolving export filter selection (scenarios=%s, labels=%s)",
        selection.scenario,
        selection.labels,
    )
    candidates = await list_runs_matching_filters_for_group(
        request=request,
        scenarios=selection.scenario,
        labels=selection.labels,
        run_id_contains=selection.run_id_contains,
        status=selection.status,
        contains_agent_id=selection.contains_agent_id,
        knob_filters=selection.parsed_knob_conditions(),
    )
    # The listing already applied these filters; the resolver re-applies them on
    # the enriched summaries so both branches share one ordering and one notion of
    # what each filter means. That second pass is what the CLI relies on, since it
    # walks the filesystem and reaches the resolver without a listing in front.
    return resolve_selection(candidates=candidates, selection=selection)
