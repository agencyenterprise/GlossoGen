"""Shared helpers for clickable per-run dots in result-viewer tabs.

Renders the frontend-base text input, builds the per-run URL, and opens the
clicked run's page in a new browser tab. Used by every tab whose plots have
points that map back to a single run.
"""

import json

import streamlit as st
import streamlit.components.v1 as components


def render_frontend_base(streamlit_key: str) -> str:
    """Text input for the frontend base URL used to build per-run links.

    Returned value is trimmed of trailing slashes. Defaults to the local dev
    server; the user can paste a Railway / production URL to deep-link into a
    deployed frontend instead.
    """
    raw = st.text_input(
        label="Frontend base URL (for run links)",
        value="http://localhost:3000",
        key=streamlit_key,
        help="Run-id dots in the chart link to "
        "`<base>/runs/<scenario>/<run_dir_name>` on this host.",
    )
    return raw.rstrip("/")


def run_url(frontend_base: str, run_id: str) -> str:
    """Build the per-run frontend URL: ``<base>/runs/<scenario>/<run_dir_name>``."""
    return f"{frontend_base}/runs/{run_id}"


def maybe_open_clicked_run(chart_event: object, session_key: str) -> None:
    """Open the most recently clicked run in a new browser tab.

    Scans the selection's points (back to front) for one with a string URL in
    ``customdata``; this lets overlapping traces (e.g. the mean trace on top
    of a replica trace) coexist — the click resolves to the first replica
    point under the cursor that carries a URL.

    De-duplicates via ``st.session_state[session_key]`` so unrelated reruns
    don't re-trigger the navigation. The actual navigation is done by
    injecting a ``window.open`` call via ``components.html`` — Streamlit has
    no native "open external URL" call.
    """
    selection = getattr(chart_event, "selection", None)
    if selection is None:
        return
    points = selection.get("points") if isinstance(selection, dict) else None
    if not points:
        return
    url: str | None = None
    for point in reversed(points):
        customdata = point.get("customdata")
        if not customdata:
            continue
        candidate = customdata[0] if isinstance(customdata, list) else customdata
        if isinstance(candidate, str) and candidate:
            url = candidate
            break
    if url is None:
        return
    if st.session_state.get(session_key) == url:
        return
    st.session_state[session_key] = url
    encoded = json.dumps(url)
    components.html(
        f"<script>window.open({encoded}, '_blank', 'noopener,noreferrer');</script>",
        height=0,
    )
    st.toast(f"opened {url}", icon="↗")
