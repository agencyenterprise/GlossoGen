"""Streamlit "Probe similarity" tab — four research-goal subtabs.

The tab is a thin shell around four sub-views, each scoped to a specific
research question about emergent agent protocols:

* **Cross-team swap** — for a cross-run replace-agent run, compare the
  imported agent's protocol against its origin (Sim B) and the
  co-acting agents' protocols against Sim A.
* **Multi-stage swap** — for a single run with one or more in-run
  agent swaps, show each agent's protocol at every probed phase
  boundary side by side.
* **Compare runs** — pick two runs that probed the same agent set and
  diff their per-question protocols.
* **Replica self-similarity** — for one run, show the N replica
  responses per (agent, question) cell sorted by lowest within-cell
  consistency (where the protocol has not crystallized yet).

All four subtabs render on the same primitive: the **text-card grid**
(:func:`_render_text_grid`), where rows are probe questions and columns
are the relevant comparison axis (cutoffs / source vs target / Run A vs
Run B / replica indices). The verbatim probe text is the primary
visual; similarity scores are small chips, not the dominant signal.
"""

import logging
from pathlib import Path
from typing import NamedTuple

import orjson
import streamlit as st
from rapidfuzz.distance import Levenshtein

from analysis.results_viewer import seed_mode_filter
from analysis.results_viewer.cross_swap_data import list_cross_swap_runs
from analysis.results_viewer.multi_swap_data import MultiSwapRun, PhaseScore, list_multi_swap_runs
from analysis.results_viewer.natural_sort import natural_sort_key
from analysis.results_viewer.probe_question_bank import get_question_prompt
from analysis.results_viewer.probe_similarity_data import (
    ProbeSimilarityRun,
    list_probe_similarity_runs,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url
from schmidt.evaluation.metrics.protocol_probe.response_models import ProtocolProbeResponse

logger = logging.getLogger(__name__)

_REPLICA_TEXT_TRUNCATE = 200
_CROSS_RUN_MANIFEST_FILENAME = "cross_run_replace_manifest.json"


class CellId(NamedTuple):
    """Unique identifier for one probe cell."""

    run_id: str
    agent_id: str
    question_id: str
    cutoff_round: int | None


class Cell(NamedTuple):
    """One agent's replica answers to a single probe question at one cutoff."""

    cell_id: CellId
    model: str
    role_name: str
    question_role_filter: str
    replicas: list[str]


class GridColumn(NamedTuple):
    """One column of the text-card grid."""

    key: str
    header_label: str
    header_caption: str


class GridCell(NamedTuple):
    """Payload for one (row, column) cell in the text-card grid.

    ``extra`` is an optional second ``(score, label)`` chip rendered after
    the primary chip — used by the cross-team 3-column grid where the
    SimC column carries comparisons against both SimA and SimB.
    """

    replicas: list[str]
    score: float | None
    score_label: str
    extra: tuple[float, str] | None


class GridRow(NamedTuple):
    """One row of the text-card grid (typically one probe question)."""

    row_key: str
    title: str
    subtitle: str
    cells_by_column_key: dict[str, GridCell]
    row_score: float | None
    row_score_label: str


def _format_cutoff(cutoff_round: int | None) -> str:
    """Human-readable label for a probe ``cutoff_round`` value."""
    if cutoff_round is None:
        return "end-of-run"
    return f"round {cutoff_round}"


def _truncate(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars, suffixing ``…`` if it was longer."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _run_picker_label(probe_run: ProbeSimilarityRun) -> str:
    """One-line picker label combining run_id, model, round count, budget, postmortem, labels."""
    if probe_run.labels:
        label_str = ",".join(probe_run.labels)
    else:
        label_str = "—"
    if probe_run.round_count is None:
        rounds_str = "r=?"
    else:
        rounds_str = f"r={probe_run.round_count}"
    if probe_run.round_time_budget_seconds is None:
        budget_str = "b=?"
    else:
        budget_str = f"b={probe_run.round_time_budget_seconds}s"
    if probe_run.postmortem_enabled:
        postmortem_str = "postmortem=on"
    else:
        postmortem_str = "postmortem=off"
    return (
        f"{probe_run.run_id} · {probe_run.primary_model} · {rounds_str}"
        f" · {budget_str} · {postmortem_str} · labels=[{label_str}]"
    )


def _self_similarity(replicas: list[str]) -> float | None:
    """Mean pairwise Levenshtein similarity across replicas; ``None`` if <2 replicas."""
    if len(replicas) < 2:
        return None
    total = 0.0
    count = 0
    for i in range(len(replicas)):
        for j in range(i + 1, len(replicas)):
            total += Levenshtein.normalized_similarity(replicas[i], replicas[j])
            count += 1
    return total / count


def _cross_cell_similarity(replicas_a: list[str], replicas_b: list[str]) -> float | None:
    """Mean Levenshtein similarity over the cartesian product of two replica sets."""
    if not replicas_a or not replicas_b:
        return None
    total = 0.0
    count = 0
    for text_a in replicas_a:
        for text_b in replicas_b:
            total += Levenshtein.normalized_similarity(text_a, text_b)
            count += 1
    return total / count


def _build_cells(probe_runs: list[ProbeSimilarityRun]) -> list[Cell]:
    """Group raw probe rows into one cell per (run, agent, question, cutoff)."""
    grouped: dict[CellId, list[ProtocolProbeResponse]] = {}
    for run in probe_runs:
        for row in run.rows:
            cell_id = CellId(
                run_id=run.run_id,
                agent_id=row.agent_id,
                question_id=row.question_id,
                cutoff_round=row.cutoff_round,
            )
            grouped.setdefault(cell_id, []).append(row)
    cells: list[Cell] = []
    for cell_id, rows in grouped.items():
        sorted_rows = sorted(rows, key=lambda row: row.replica_index)
        head = sorted_rows[0]
        cells.append(
            Cell(
                cell_id=cell_id,
                model=head.model,
                role_name=head.role_name,
                question_role_filter=head.question_role_filter,
                replicas=[row.response_text for row in sorted_rows],
            )
        )
    return cells


def _cells_by_aqc(cells: list[Cell]) -> dict[tuple[str, str, str, int | None], Cell]:
    """Index by ``(run_id, agent_id, question_id, cutoff_round)``."""
    return {
        (
            cell.cell_id.run_id,
            cell.cell_id.agent_id,
            cell.cell_id.question_id,
            cell.cell_id.cutoff_round,
        ): cell
        for cell in cells
    }


def _agents_in_run(run: ProbeSimilarityRun) -> set[str]:
    """Distinct agent_ids that appear in this run's probe rows."""
    return {row.agent_id for row in run.rows}


def _questions_for_agent(
    cells: list[Cell],
    *,
    run_id: str,
    agent_id: str,
) -> list[str]:
    """Return the probe question_ids for one (run, agent), sorted by id."""
    matched = {
        cell.cell_id.question_id
        for cell in cells
        if cell.cell_id.run_id == run_id and cell.cell_id.agent_id == agent_id
    }
    return sorted(matched, key=natural_sort_key)


def _is_single_team_run(probe_run: ProbeSimilarityRun) -> bool:
    """Return ``True`` for runs whose probe data captures a single, non-imported team.

    Replica self-similarity asks "does this agent give the same answer
    across replicas?" — a question that only makes sense when the agent's
    history is uncontaminated by team-swap dynamics. We exclude:

    * Cross-run replace-agent runs (presence of
      ``cross_run_replace_manifest.json``), where one agent was lifted
      from another run mid-play.
    * Two-team runs, detectable via two or more distinct ``agent_id``
      values sharing the same ``role_name`` in the probe rows.
    """
    if (probe_run.run_dir / _CROSS_RUN_MANIFEST_FILENAME).exists():
        return False
    agents_per_role: dict[str, set[str]] = {}
    for row in probe_run.rows:
        agents_per_role.setdefault(row.role_name, set()).add(row.agent_id)
    return all(len(agents) <= 1 for agents in agents_per_role.values())


def _read_cross_team_replaced_agent_id(run_dir: Path) -> str | None:
    """Read ``replaced_agent_id`` out of ``cross_run_replace_manifest.json``."""
    manifest_path = run_dir / _CROSS_RUN_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        raw = orjson.loads(manifest_path.read_bytes())
    except Exception:
        logger.exception("Failed to parse cross-run manifest at %s", manifest_path)
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("replaced_agent_id")
    if not isinstance(value, str):
        return None
    return value


def _median(values: list[float]) -> float | None:
    """Return the median of ``values``; ``None`` when the list is empty."""
    if not values:
        return None
    sorted_values = sorted(values)
    count = len(sorted_values)
    middle = count // 2
    if count % 2 == 1:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def _mean(values: list[float]) -> float | None:
    """Return the arithmetic mean of ``values``; ``None`` when the list is empty."""
    if not values:
        return None
    return sum(values) / len(values)


_SATURATED_THRESHOLD = 0.99


def _format_median_mean(values: list[float]) -> tuple[str, str]:
    """Return ``(value_text, delta_text)`` for an ``st.metric`` summary tile.

    The big value is the median; the delta sub-line carries the mean and a
    "saturated" count — the fraction of cells with similarity at or above
    :data:`_SATURATED_THRESHOLD`. Both extra numbers help disambiguate the
    median when the underlying distribution is bimodal.
    """
    median_score = _median(values=values)
    mean_score = _mean(values=values)
    value_text = "—" if median_score is None else f"{median_score:.2f}"
    if mean_score is None:
        delta_text = "mean — · sat —"
    else:
        saturated = sum(1 for value in values if value >= _SATURATED_THRESHOLD)
        delta_text = f"mean {mean_score:.2f} · {saturated}/{len(values)} sat"
    return value_text, delta_text


def _render_subtab_help(*, title: str, body: str) -> None:
    """Render a top-of-subtab title with an inline ``ⓘ`` popover."""
    title_col, info_col = st.columns([12, 1])
    with title_col:
        st.markdown(f"#### {title}")
    with info_col:
        st.markdown("&nbsp;")
        with st.popover("ⓘ", help="What this view shows"):
            st.markdown(body)


_CROSS_TEAM_HELP_BODY = (
    "For one cross-run replace-agent run, this view shows each probed "
    "agent's protocol at three points side by side: **SimA** (the host "
    "timeline), **SimB** (the imported agent's origin), and **SimC** "
    "(the cross-run run itself). The same `agent_id` is followed across "
    "all three runs, so the SimA cell shows what the *displaced* "
    "predecessor was speaking and the SimB cell shows what the *foreign "
    "team's* same-role agent was speaking.\n\n"
    "**Rows** are probe questions; each row begins with the question id "
    "and its prompt (e.g. `symptoms: ...` for observer questions).\n\n"
    "**Columns** are SimA · SimB · SimC. The SimC cell carries two "
    "chips: `vs SimA` (mean Levenshtein similarity over the cartesian "
    "product of SimA × SimC replicas) and `vs SimB` (same against SimB). "
    "Saturation at `1.00` means the protocol matches that origin "
    "unchanged; lower scores indicate drift.\n\n"
    "**All three probes are read at `cutoff_round = null` (end of run).** "
    "For SimB that means the protocol the foreign team converged to by "
    "*its* last round — which only matches what the imported agent "
    "actually carried into SimC when `source_b_round_end == B_max_round`. "
    "If SimB kept playing past the extraction point, re-probe SimB with "
    "`--probe-round source_b_round_end` to get a snapshot matched to the "
    "moment the agent was lifted out.\n\n"
    "Two row-groups are rendered: the imported agent and every other "
    "probed agent. All three runs must have probe data — re-run "
    "`schmidt evaluate ... --metrics protocol_probe` on any missing source "
    "if the warning fires."
)

_CROSS_TEAM_OVERVIEW_PROSE = (
    "A cross-team swap takes one agent out of **SimB** at the end of "
    "round `source_b_round_end` and drops it into **SimA** at the start "
    "of round `round_start`, producing **SimC** (the run we're looking at). "
    "The imported agent keeps its full pydantic-ai history from SimB "
    "(every message, every thought) — it walks into SimA's environment "
    "remembering everything it learned with its old teammates. The two "
    "row groups below show how each agent's protocol compares across the "
    "three sims:"
)

_CROSS_TEAM_IMPORTED_PROSE = (
    "Each row is one probe question. The **SimA** column shows what the "
    "*displaced* same-role predecessor was answering at the end of "
    "`{source_a_run_id}` — the protocol the imported agent's new "
    "teammates were used to. The **SimB** column shows what the "
    "imported agent (`{replaced_agent_id}`) was answering at the end of "
    "its origin `{source_b_run_id}` — the protocol it brought into "
    "SimC. The **SimC** column shows what the imported agent answered "
    "after playing the rest of SimC alongside SimA's teammates.\n\n"
    "**SimC chips:** `vs SimA` and `vs SimB` are each the mean "
    "Levenshtein similarity over the cartesian product of replicas "
    "between SimC and that origin. The row title carries `min sim`, "
    "the smaller of the two — rows are sorted lowest-min-first so the "
    "questions where the imported agent diverged most from at least one "
    "origin surface at the top.\n\n"
    "**High `vs SimB`** — the imported agent kept emitting its origin "
    "protocol after the swap, i.e. its protocol *persisted*.\n"
    "**High `vs SimA`** — the imported agent's responses match what "
    "its new teammates were used to, i.e. it *adapted* (or the two "
    "teams independently converged on the same protocol).\n"
    "**Both low** — the imported agent drifted into something neither "
    "team was speaking.\n"
    "**Both high** — both source teams independently converged on the "
    "same protocol; the swap had nothing to disrupt.\n\n"
    "**Caveat on the SimB side:** the comparison uses SimB's end-of-run "
    "probe, not a probe taken at the extraction round "
    "(`source_b_round_end`). When SimB kept playing past the "
    "extraction point, this snapshot reflects SimB's final protocol "
    "rather than what the imported agent actually carried over."
)

_CROSS_TEAM_CO_ACTORS_PROSE = (
    "These are every probed agent in SimC *other than* "
    "`{replaced_agent_id}` — i.e. every agent that stayed in "
    "`{source_a_run_id}` across the swap boundary. The **SimA** column "
    "shows what the agent answered at the end of its original SimA run; "
    "the **SimB** column shows what the *foreign team's* same-role "
    "agent was answering at the end of `{source_b_run_id}` (a different "
    "physical agent, same `agent_id`); the **SimC** column shows what "
    "the staying agent answered after the swap played out.\n\n"
    "**SimC chips:** `vs SimA` (did the staying agent retain its "
    "original protocol?) and `vs SimB` (did it shift toward what the "
    "foreign team's same-role agent was speaking?). The row title's "
    "`min sim` is the smaller of the two; rows are sorted "
    "lowest-min-first so the questions where the staying agent "
    "diverged most surface at the top.\n\n"
    "**High `vs SimA`** — the co-acting agent kept its original "
    "protocol despite the new face at the table.\n"
    "**High `vs SimB`** — the co-acting agent's protocol now matches "
    "the foreign team — either *accommodation* to the imported agent "
    "or independent convergence between the two teams."
)

_MULTI_SWAP_HELP_BODY = (
    "For one run with one or more in-run agent swaps, this view shows "
    "each agent's probe protocol at every probed phase boundary side by "
    "side.\n\n"
    "**Phase columns** map to probe cutoffs: the cutoff that captures "
    "the protocol *as it stood when that phase ended* (the round before "
    "the next swap, or end-of-run for the last phase).\n\n"
    "**Score chip** on column k≥2 is the mean Levenshtein similarity "
    "between phase k-1's replicas and phase k's replicas at that probe "
    "question — i.e. how much the protocol shifted across that swap.\n\n"
    "**Per-phase medians** at the top condense the same data into one "
    "number per phase transition. High median = the protocol persisted "
    "across the swap; low = the swap disrupted it.\n\n"
    "Probe data must exist at each phase boundary cutoff — re-run "
    "`schmidt evaluate ... --metrics protocol_probe --probe-round R "
    "--probe-replicas N` for any cutoff the banner flags as missing."
)

_COMPARE_RUNS_HELP_BODY = (
    "Pick two runs that probed the same agent set; this view renders "
    "one row per probe question with both runs' verbatim responses side "
    "by side.\n\n"
    "**Run B is constrained** to runs whose set of probed `agent_id` "
    "values is identical to Run A's. This rules out cross-comparing a "
    "two-team run against a single-team run (their agent ids differ).\n\n"
    "**Score chip** on the Run B column is the mean cross-replica "
    "Levenshtein similarity between Run A's replicas and Run B's "
    "replicas for that question. Saturation at `1.00` means both runs "
    "converged on the same surface form; lower scores mean their "
    "protocols diverged.\n\n"
    "**Per-agent medians** at the top condense the same data into one "
    "number per agent (plus an overall median across all agents). "
    "High median = the two runs converged on a similar protocol for "
    "this agent; low = they diverged.\n\n"
    "Rows are sorted lowest-similarity-first so divergent questions "
    "surface at the top."
)

_REPLICA_SELF_HELP_BODY = (
    "For one run, this view shows each agent's N replica answers per "
    "probe question side by side.\n\n"
    "**Row score chip** is the mean pairwise Levenshtein similarity "
    "between the replica responses inside one cell. Saturation at "
    "`1.00` means every replica produced the same surface form — the "
    "agent's protocol has crystallized for that question. Below `1.00` "
    "means the agent has not converged on a single answer.\n\n"
    "**Per-agent medians** at the top condense the same data into one "
    "number per agent (plus an overall median across all agents). High "
    "median = the agent's protocol is converged across most questions; "
    "low = many questions still have replica disagreement.\n\n"
    "Rows are sorted lowest-similarity-first so non-converged questions "
    "surface at the top.\n\n"
    "When the run was probed at multiple cutoffs (`--probe-round R` "
    "across rounds), pick which cutoff snapshot to inspect.\n\n"
    "**Single-team runs only.** Cross-run replace-agent runs and "
    "two-team runs are excluded — those mix histories from different "
    "teams, so a single replica-self number per agent doesn't answer a "
    "clean question. Use the Cross-team swap or Multi-stage swap "
    "subtabs for those workflows."
)


def _score_chip(score: float | None, *, label: str) -> str:
    """Return an HTML chip rendering a similarity score with a traffic-light color.

    Returns a muted span (no background) when ``score`` is ``None`` so
    cells with missing data degrade gracefully.
    """
    if score is None:
        return f"<span style='color:#888;font-size:0.85em'>{label}: —</span>"
    if score < 0.30:
        background = "#ffcdd2"
        foreground = "#b71c1c"
    elif score < 0.70:
        background = "#fff8c5"
        foreground = "#7a5b00"
    else:
        background = "#c8e6c9"
        foreground = "#1b5e20"
    return (
        f"<span style='display:inline-block;padding:1px 6px;border-radius:6px;"
        f"background:{background};color:{foreground};font-size:0.80em;"
        f"font-weight:600'>{label}: {score:.2f}</span>"
    )


def _render_grid_cell(cell: GridCell | None) -> None:
    """Render one (row, column) cell — verbatim replicas plus a score chip."""
    if cell is None or not cell.replicas:
        st.markdown(
            "<span style='color:#888;font-style:italic;font-size:0.85em'>(no data)</span>",
            unsafe_allow_html=True,
        )
        return
    body_html = "<br>".join(
        f"<code style='font-size:0.85em;white-space:pre-wrap;display:inline-block;"
        f"max-width:100%'>{_truncate(text=text, limit=_REPLICA_TEXT_TRUNCATE)}</code>"
        for text in cell.replicas
    )
    chip = _score_chip(score=cell.score, label=cell.score_label)
    if cell.extra is None:
        chips_html = chip
    else:
        extra_score, extra_label = cell.extra
        extra_chip = _score_chip(score=extra_score, label=extra_label)
        chips_html = f"{chip}&nbsp;&nbsp;{extra_chip}"
    st.markdown(
        f"<div style='font-size:0.90em'>{body_html}</div>"
        f"<div style='margin-top:4px'>{chips_html}</div>"
        f"<div style='color:#888;font-size:0.75em;margin-top:2px'>"
        f"{len(cell.replicas)} replica(s)</div>",
        unsafe_allow_html=True,
    )


def _render_text_grid(
    *,
    columns: list[GridColumn],
    rows: list[GridRow],
) -> None:
    """Render the question × column text-card grid."""
    if not rows:
        st.info("No probe questions to render in this view.")
        return
    column_count = len(columns)
    weights = [3, *([4] * column_count)]
    header_slots = st.columns(weights)
    header_slots[0].markdown("**Question**")
    for index, column in enumerate(columns):
        with header_slots[index + 1]:
            st.markdown(f"**{column.header_label}**")
            if column.header_caption:
                st.caption(column.header_caption)
    st.markdown(
        "<hr style='margin:4px 0 8px 0;border:none;border-top:1px solid #ccc'>",
        unsafe_allow_html=True,
    )
    for row in rows:
        with st.container(border=True):
            row_slots = st.columns(weights)
            with row_slots[0]:
                title_html = f"<strong>{row.title}</strong>"
                if row.row_score is not None:
                    title_html += "&nbsp;&nbsp;" + _score_chip(
                        score=row.row_score, label=row.row_score_label
                    )
                st.markdown(title_html, unsafe_allow_html=True)
                if row.subtitle:
                    st.caption(row.subtitle)
            for index, column in enumerate(columns):
                with row_slots[index + 1]:
                    _render_grid_cell(cell=row.cells_by_column_key.get(column.key))


def _build_question_row(
    *,
    scenario_name: str,
    question_id: str,
    cells_by_column_key: dict[str, GridCell],
    row_score: float | None,
    row_score_label: str,
) -> GridRow:
    """Wrap a per-column cell map into a ``GridRow`` keyed by question id."""
    prompt = get_question_prompt(scenario_name=scenario_name, question_id=question_id)
    return GridRow(
        row_key=question_id,
        title=question_id,
        subtitle=prompt.display_text,
        cells_by_column_key=cells_by_column_key,
        row_score=row_score,
        row_score_label=row_score_label,
    )


# ---- Subtab: Replica self-similarity ----------------------------------------


def _render_replica_self_subtab(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Show one (agent, question) row per cell with replicas as side-by-side columns."""
    _render_subtab_help(title="Replica self-similarity", body=_REPLICA_SELF_HELP_BODY)
    runs_with_data = [run for run in probe_runs if run.rows and _is_single_team_run(probe_run=run)]
    if not runs_with_data:
        st.info(
            "No single-team runs with `protocol_probe_responses.jsonl` available. "
            "Cross-team and two-team runs are excluded from this view — see the "
            "Cross-team swap or Multi-stage swap subtabs instead."
        )
        return
    options = {_run_picker_label(probe_run=run): run for run in runs_with_data}
    chosen_label = st.selectbox(
        label="Run",
        options=list(options.keys()),
        index=0,
        key="probe_replica_self_run",
    )
    chosen_run = options[chosen_label]
    frontend_base = render_frontend_base(streamlit_key="probe_replica_self_frontend_base")
    target_url = run_url(frontend_base=frontend_base, run_id=chosen_run.run_id)
    st.markdown(f"[Open run in frontend ↗]({target_url})")
    cells = _build_cells(probe_runs=[chosen_run])
    if not cells:
        st.info("No probe rows in the chosen run.")
        return
    cutoff_values = sorted(
        {cell.cell_id.cutoff_round for cell in cells},
        key=lambda value: (value is None, value if value is not None else 0),
    )
    if len(cutoff_values) > 1:
        cutoff_options = {_format_cutoff(cutoff_round=value): value for value in cutoff_values}
        chosen_cutoff_label = st.selectbox(
            label="Cutoff snapshot",
            options=list(cutoff_options.keys()),
            index=len(cutoff_values) - 1,
            key="probe_replica_self_cutoff",
        )
        chosen_cutoff = cutoff_options[chosen_cutoff_label]
    else:
        chosen_cutoff = cutoff_values[0]
    cells_at_cutoff = [cell for cell in cells if cell.cell_id.cutoff_round == chosen_cutoff]
    if not cells_at_cutoff:
        st.info("No cells at the chosen cutoff.")
        return
    agent_ids = sorted({cell.cell_id.agent_id for cell in cells_at_cutoff})
    grids_per_agent: dict[str, _ReplicaSelfAgentGrid] = {}
    scores_per_agent: dict[str, list[float]] = {}
    for agent_id in agent_ids:
        agent_cells = [cell for cell in cells_at_cutoff if cell.cell_id.agent_id == agent_id]
        max_replicas = max(len(cell.replicas) for cell in agent_cells)
        columns = [
            GridColumn(key=f"r{index + 1}", header_label=f"r{index + 1}", header_caption="")
            for index in range(max_replicas)
        ]
        rows: list[GridRow] = []
        for cell in agent_cells:
            cells_by_column_key: dict[str, GridCell] = {}
            self_score = _self_similarity(replicas=cell.replicas)
            for index, replica_text in enumerate(cell.replicas):
                cells_by_column_key[f"r{index + 1}"] = GridCell(
                    replicas=[replica_text],
                    score=None,
                    score_label="",
                    extra=None,
                )
            rows.append(
                _build_question_row(
                    scenario_name=chosen_run.scenario_name,
                    question_id=cell.cell_id.question_id,
                    cells_by_column_key=cells_by_column_key,
                    row_score=self_score,
                    row_score_label="self-sim",
                )
            )
            if self_score is not None:
                scores_per_agent.setdefault(agent_id, []).append(self_score)
        rows.sort(key=lambda row: natural_sort_key(row.row_key))
        head = agent_cells[0]
        grids_per_agent[agent_id] = _ReplicaSelfAgentGrid(
            heading=(
                f"### {agent_id} · {head.role_name} · `{head.model}`"
                f" · cutoff {_format_cutoff(cutoff_round=chosen_cutoff)}"
            ),
            columns=columns,
            rows=rows,
        )
    _render_replica_self_medians(scores_per_agent=scores_per_agent)
    st.markdown("---")
    for agent_grid in grids_per_agent.values():
        st.markdown(agent_grid.heading)
        _render_text_grid(columns=agent_grid.columns, rows=agent_grid.rows)


class _ReplicaSelfAgentGrid(NamedTuple):
    """Buffered render payload for one agent's replica-self grid."""

    heading: str
    columns: list[GridColumn]
    rows: list[GridRow]


def _render_replica_self_medians(*, scores_per_agent: dict[str, list[float]]) -> None:
    """Render a row of ``st.metric`` tiles with overall + per-agent median self-similarity."""
    all_scores: list[float] = []
    for scores in scores_per_agent.values():
        all_scores.extend(scores)
    if not all_scores:
        return
    sorted_agents = sorted(scores_per_agent.items())
    metric_cols = st.columns(len(sorted_agents) + 1)
    overall_value, overall_delta = _format_median_mean(values=all_scores)
    metric_cols[0].metric(
        label="Overall · median self-sim",
        value=overall_value,
        delta=overall_delta,
        delta_color="off",
    )
    for index, (agent_id, scores) in enumerate(sorted_agents):
        agent_value, agent_delta = _format_median_mean(values=scores)
        metric_cols[index + 1].metric(
            label=f"{agent_id} · median",
            value=agent_value,
            delta=agent_delta,
            delta_color="off",
        )


# ---- Subtab: Compare runs ---------------------------------------------------


def _render_compare_runs_subtab(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Pick two runs that probed the same agent set and diff their protocols."""
    _render_subtab_help(title="Compare runs", body=_COMPARE_RUNS_HELP_BODY)
    runs_with_data = [run for run in probe_runs if run.rows]
    if len(runs_with_data) < 2:
        st.info("Need at least two runs with probe data to compare.")
        return
    run_a_options = {_run_picker_label(probe_run=run): run for run in runs_with_data}
    chosen_a_label = st.selectbox(
        label="Run A",
        options=list(run_a_options.keys()),
        index=0,
        key="probe_compare_run_a",
    )
    run_a = run_a_options[chosen_a_label]
    agents_a = _agents_in_run(run=run_a)
    candidates_b = [
        run
        for run in runs_with_data
        if run.run_id != run_a.run_id and _agents_in_run(run=run) == agents_a
    ]
    if not candidates_b:
        st.info(
            "No comparable runs (no other run probed the same agent set "
            f"as {run_a.run_id}). Pick a different Run A or run probes "
            "on a comparable run."
        )
        return
    run_b_options = {_run_picker_label(probe_run=run): run for run in candidates_b}
    chosen_b_label = st.selectbox(
        label="Run B",
        options=list(run_b_options.keys()),
        index=0,
        key="probe_compare_run_b",
    )
    run_b = run_b_options[chosen_b_label]
    frontend_base = render_frontend_base(streamlit_key="probe_compare_frontend_base")
    run_a_url = run_url(frontend_base=frontend_base, run_id=run_a.run_id)
    run_b_url = run_url(frontend_base=frontend_base, run_id=run_b.run_id)
    st.markdown(
        f"[Open Run A in frontend ↗]({run_a_url}) · [Open Run B in frontend ↗]({run_b_url})"
    )
    cells = _build_cells(probe_runs=[run_a, run_b])
    cells_at_eor = [cell for cell in cells if cell.cell_id.cutoff_round is None]
    if not cells_at_eor:
        st.info("Neither run has end-of-run probes (cutoff_round=null).")
        return
    cells_index = _cells_by_aqc(cells=cells_at_eor)
    columns = [
        GridColumn(
            key="run_a",
            header_label=run_a.run_id,
            header_caption=run_a.primary_model,
        ),
        GridColumn(
            key="run_b",
            header_label=run_b.run_id,
            header_caption=run_b.primary_model,
        ),
    ]
    rows_per_agent: dict[str, list[GridRow]] = {}
    scores_per_agent: dict[str, list[float]] = {}
    for agent_id in sorted(agents_a):
        question_ids = sorted(
            {
                cell.cell_id.question_id
                for cell in cells_at_eor
                if cell.cell_id.agent_id == agent_id
            },
            key=natural_sort_key,
        )
        rows: list[GridRow] = []
        for question_id in question_ids:
            cell_a = cells_index.get((run_a.run_id, agent_id, question_id, None))
            cell_b = cells_index.get((run_b.run_id, agent_id, question_id, None))
            if cell_a is None or cell_b is None:
                continue
            score = _cross_cell_similarity(replicas_a=cell_a.replicas, replicas_b=cell_b.replicas)
            cells_by_column_key = {
                "run_a": GridCell(replicas=cell_a.replicas, score=None, score_label="", extra=None),
                "run_b": GridCell(
                    replicas=cell_b.replicas, score=score, score_label="sim to A", extra=None
                ),
            }
            rows.append(
                _build_question_row(
                    scenario_name=run_a.scenario_name,
                    question_id=question_id,
                    cells_by_column_key=cells_by_column_key,
                    row_score=score,
                    row_score_label="sim",
                )
            )
            if score is not None:
                scores_per_agent.setdefault(agent_id, []).append(score)
        rows.sort(key=lambda row: natural_sort_key(row.row_key))
        if rows:
            rows_per_agent[agent_id] = rows
    _render_compare_runs_medians(scores_per_agent=scores_per_agent)
    st.markdown("---")
    for agent_id, agent_rows in rows_per_agent.items():
        st.markdown(f"### {agent_id}")
        _render_text_grid(columns=columns, rows=agent_rows)


def _render_compare_runs_medians(*, scores_per_agent: dict[str, list[float]]) -> None:
    """Render a row of ``st.metric`` tiles with overall + per-agent median similarity."""
    all_scores: list[float] = []
    for scores in scores_per_agent.values():
        all_scores.extend(scores)
    if not all_scores:
        return
    sorted_agents = sorted(scores_per_agent.items())
    metric_cols = st.columns(len(sorted_agents) + 1)
    overall_value, overall_delta = _format_median_mean(values=all_scores)
    metric_cols[0].metric(
        label="Overall · median similarity",
        value=overall_value,
        delta=overall_delta,
        delta_color="off",
    )
    for index, (agent_id, scores) in enumerate(sorted_agents):
        agent_value, agent_delta = _format_median_mean(values=scores)
        metric_cols[index + 1].metric(
            label=f"{agent_id} · median",
            value=agent_value,
            delta=agent_delta,
            delta_color="off",
        )


# ---- Subtab: Multi-stage swap -----------------------------------------------


class _PhaseColumn(NamedTuple):
    """One probed phase boundary mapped to a grid column."""

    phase: PhaseScore
    cutoff_round: int | None
    column_key: str
    header_label: str
    header_caption: str


def _expected_cutoff_for_phase(*, phase: PhaseScore, phases: list[PhaseScore]) -> int | None:
    """The probe ``cutoff_round`` capturing the protocol *as it stood when ``phase`` ended*.

    The probe metric defines ``cutoff_round=R`` as "history covers rounds
    1..R-1 inclusive" — i.e. the probe was taken at the *start* of
    round R. To capture the protocol at the end of a phase whose last
    round is ``phase.round_end``, the matching probe cutoff is
    ``phase.round_end + 1`` (= the start of the next phase, which is
    when the swap fired). For the last phase we use ``None``
    (end-of-run probe).
    """
    is_last = phase.phase_index == len(phases) - 1
    if is_last:
        return None
    return phase.round_end + 1


def _build_phase_columns(
    *,
    phases: list[PhaseScore],
    available_cutoffs: set[int | None],
) -> tuple[list[_PhaseColumn], list[PhaseScore]]:
    """Return one column per phase that has matching probe rows; also report missing phases."""
    columns: list[_PhaseColumn] = []
    missing: list[PhaseScore] = []
    for phase in phases:
        expected = _expected_cutoff_for_phase(phase=phase, phases=phases)
        if expected not in available_cutoffs:
            missing.append(phase)
            continue
        if phase.swap is None:
            header_label = phase.label
            header_caption = (
                f"rounds {phase.round_start}–{phase.round_end} · cutoff "
                f"{_format_cutoff(cutoff_round=expected)}"
            )
        else:
            header_label = f"Phase {chr(ord('A') + phase.phase_index)}"
            header_caption = (
                f"swap {phase.swap.agent_id} → {phase.swap.new_model}"
                f" · rounds {phase.round_start}–{phase.round_end}"
                f" · cutoff {_format_cutoff(cutoff_round=expected)}"
            )
        columns.append(
            _PhaseColumn(
                phase=phase,
                cutoff_round=expected,
                column_key=f"phase_{phase.phase_index}",
                header_label=header_label,
                header_caption=header_caption,
            )
        )
    return columns, missing


def _build_agent_rows_for_multi_swap(
    *,
    scenario_name: str,
    agent_id: str,
    probe_run_id: str,
    phase_columns: list[_PhaseColumn],
    cells: list[Cell],
    cells_index: dict[tuple[str, str, str, int | None], Cell],
    transition_scores: list[list[float]],
) -> list[GridRow]:
    """Build the GridRows for one agent and append per-phase scores into ``transition_scores``."""
    question_ids = _questions_for_agent(cells=cells, run_id=probe_run_id, agent_id=agent_id)
    rows: list[GridRow] = []
    for question_id in question_ids:
        phase_cells: list[Cell | None] = [
            cells_index.get((probe_run_id, agent_id, question_id, phase_column.cutoff_round))
            for phase_column in phase_columns
        ]
        cells_by_column_key: dict[str, GridCell] = {}
        for index, phase_column in enumerate(phase_columns):
            phase_cell = phase_cells[index]
            if phase_cell is None:
                continue
            if index == 0:
                score = _self_similarity(replicas=phase_cell.replicas)
                score_label = "self-sim"
            else:
                previous = phase_cells[index - 1]
                if previous is None:
                    score = None
                    score_label = "vs prev"
                else:
                    score = _cross_cell_similarity(
                        replicas_a=previous.replicas, replicas_b=phase_cell.replicas
                    )
                    score_label = "vs prev"
            if score is not None:
                transition_scores[index].append(score)
            cells_by_column_key[phase_column.column_key] = GridCell(
                replicas=phase_cell.replicas,
                score=score,
                score_label=score_label,
                extra=None,
            )
        if cells_by_column_key:
            rows.append(
                _build_question_row(
                    scenario_name=scenario_name,
                    question_id=question_id,
                    cells_by_column_key=cells_by_column_key,
                    row_score=None,
                    row_score_label="",
                )
            )
    return rows


def _render_multi_swap_medians(
    *,
    phase_columns: list[_PhaseColumn],
    transition_scores: list[list[float]],
) -> None:
    """Render a row of ``st.metric`` tiles: one median per phase column.

    Column 0's tile shows the within-phase replica self-similarity
    median (a baseline of *how converged* the protocol was during the
    initial phase). Columns k≥1 show median similarity between
    phase k-1 and phase k — the *drift* across that swap. A trailing
    "Overall (k≥1)" tile aggregates the cross-phase medians.
    """
    cross_phase_scores: list[float] = []
    for index, scores in enumerate(transition_scores):
        if index >= 1:
            cross_phase_scores.extend(scores)
    tile_count = len(phase_columns) + (1 if len(phase_columns) > 1 else 0)
    metric_cols = st.columns(tile_count)
    for index, phase_column in enumerate(phase_columns):
        if index == 0:
            label = f"{phase_column.header_label} · median self-sim"
        else:
            label = f"{phase_column.header_label} · median vs prev"
        value_text, delta_text = _format_median_mean(values=transition_scores[index])
        metric_cols[index].metric(
            label=label, value=value_text, delta=delta_text, delta_color="off"
        )
    if len(phase_columns) > 1:
        overall_value, overall_delta = _format_median_mean(values=cross_phase_scores)
        metric_cols[-1].metric(
            label="Overall median (k≥1)",
            value=overall_value,
            delta=overall_delta,
            delta_color="off",
        )


def _render_multi_swap_subtab(
    probe_runs: list[ProbeSimilarityRun],
    multi_swap_runs: list[MultiSwapRun],
) -> None:
    """For one multi-swap run, show each agent's protocol per probed phase."""
    _render_subtab_help(title="Multi-stage swap", body=_MULTI_SWAP_HELP_BODY)
    probe_run_by_id = {run.run_id: run for run in probe_runs if run.rows}
    eligible = [run for run in multi_swap_runs if run.run_id in probe_run_by_id]
    if not eligible:
        st.info(
            "No runs found that have both an in-run agent swap and probe "
            "rows. Run `schmidt evaluate ... --metrics protocol_probe` on "
            "a multi-swap run first."
        )
        return
    options = {
        f"{run.run_id} · {run.primary_model} · {len(run.swaps)} swap(s)": run for run in eligible
    }
    chosen_label = st.selectbox(
        label="Run",
        options=list(options.keys()),
        index=0,
        key="probe_multi_swap_run",
    )
    multi_swap = options[chosen_label]
    probe_run = probe_run_by_id[multi_swap.run_id]
    frontend_base = render_frontend_base(streamlit_key="probe_multi_swap_frontend_base")
    target_url = run_url(frontend_base=frontend_base, run_id=multi_swap.run_id)
    st.markdown(f"[Open run in frontend ↗]({target_url})")
    available_cutoffs = {row.cutoff_round for row in probe_run.rows}
    phase_columns, missing_phases = _build_phase_columns(
        phases=multi_swap.phases, available_cutoffs=available_cutoffs
    )
    if missing_phases:
        missing_parts: list[str] = []
        for phase in missing_phases:
            expected = _expected_cutoff_for_phase(phase=phase, phases=multi_swap.phases)
            missing_parts.append(
                f"{phase.label} (expected cutoff {_format_cutoff(cutoff_round=expected)})"
            )
        missing_summary = ", ".join(missing_parts)
        st.info(
            f"Phase boundaries probed: {len(phase_columns)}/{len(multi_swap.phases)}. "
            f"Missing: {missing_summary}. Re-run "
            "`schmidt evaluate ... --metrics protocol_probe --probe-round R --probe-replicas N` "
            "for each missing round to populate this view."
        )
    if not phase_columns:
        return
    columns = [
        GridColumn(
            key=phase_column.column_key,
            header_label=phase_column.header_label,
            header_caption=phase_column.header_caption,
        )
        for phase_column in phase_columns
    ]
    cells = _build_cells(probe_runs=[probe_run])
    cells_index = _cells_by_aqc(cells=cells)
    agent_ids = sorted({cell.cell_id.agent_id for cell in cells})
    transition_scores: list[list[float]] = [[] for _ in phase_columns]
    rows_per_agent: dict[str, list[GridRow]] = {}
    for agent_id in agent_ids:
        agent_rows = _build_agent_rows_for_multi_swap(
            scenario_name=probe_run.scenario_name,
            agent_id=agent_id,
            probe_run_id=probe_run.run_id,
            phase_columns=phase_columns,
            cells=cells,
            cells_index=cells_index,
            transition_scores=transition_scores,
        )
        if agent_rows:
            rows_per_agent[agent_id] = agent_rows
    _render_multi_swap_medians(phase_columns=phase_columns, transition_scores=transition_scores)
    st.markdown("---")
    for agent_id, agent_rows in rows_per_agent.items():
        head_cell = next(cell for cell in cells if cell.cell_id.agent_id == agent_id)
        st.markdown(f"### {agent_id} · {head_cell.role_name} · `{head_cell.model}`")
        _render_text_grid(columns=columns, rows=agent_rows)


# ---- Subtab: Cross-team swap ------------------------------------------------


class _CrossTeamContext(NamedTuple):
    """Loaded probe data for one cross-team triple (target, source A, source B)."""

    target: ProbeSimilarityRun
    source_a: ProbeSimilarityRun
    source_b: ProbeSimilarityRun
    replaced_agent_id: str
    round_start: int


def _resolve_cross_team_context(
    *,
    target_run: ProbeSimilarityRun,
    target_run_dir: Path,
    source_a_run_id: str,
    source_b_run_id: str,
    round_start: int,
    probe_runs_by_id: dict[str, ProbeSimilarityRun],
) -> _CrossTeamContext | None:
    """Locate probe data for both sources; return ``None`` (and log) if either is missing."""
    replaced_agent_id = _read_cross_team_replaced_agent_id(run_dir=target_run_dir)
    if replaced_agent_id is None:
        st.warning(f"Cross-run manifest for {target_run.run_id} is missing or malformed.")
        return None
    source_a = probe_runs_by_id.get(source_a_run_id)
    source_b = probe_runs_by_id.get(source_b_run_id)
    missing: list[str] = []
    if source_a is None or not source_a.rows:
        missing.append(f"source A ({source_a_run_id})")
    if source_b is None or not source_b.rows:
        missing.append(f"source B ({source_b_run_id})")
    if missing or source_a is None or source_b is None:
        st.warning(
            "Cannot render the cross-team comparison: missing probe data for "
            + ", ".join(missing or ["unknown"])
            + ". Run `schmidt evaluate ... --metrics protocol_probe` on the "
            "missing source run(s) first."
        )
        return None
    return _CrossTeamContext(
        target=target_run,
        source_a=source_a,
        source_b=source_b,
        replaced_agent_id=replaced_agent_id,
        round_start=round_start,
    )


class _CrossTeamSectionScores(NamedTuple):
    """Per-question similarity score lists for one cross-team section.

    ``vs_a`` is each rendered question's SimC↔SimA cartesian-product
    similarity; ``vs_b`` is the SimC↔SimB similarity. Both lists are
    aligned one-per-rendered-question (matching scores are dropped
    together when a question is missing from any of the three runs).
    """

    vs_a: list[float]
    vs_b: list[float]


def _render_cross_team_grid(
    *,
    target: ProbeSimilarityRun,
    source_a: ProbeSimilarityRun,
    source_b: ProbeSimilarityRun,
    agent_ids: list[str],
    section_title: str,
    section_explanation: str,
) -> _CrossTeamSectionScores:
    """Render one 3-column SimA · SimB · SimC grid and return per-question score lists.

    The SimC cell carries two chips — ``vs SimA`` and ``vs SimB`` —
    each the cartesian-product Levenshtein similarity between SimC's
    replicas and the matching origin run's same-``agent_id`` end-of-run
    replicas.
    """
    cells = _build_cells(probe_runs=[target, source_a, source_b])
    cells_index = _cells_by_aqc(cells=cells)
    columns = [
        GridColumn(
            key="sim_a",
            header_label=f"SimA · {source_a.run_id}",
            header_caption=source_a.primary_model,
        ),
        GridColumn(
            key="sim_b",
            header_label=f"SimB · {source_b.run_id}",
            header_caption=source_b.primary_model,
        ),
        GridColumn(
            key="sim_c",
            header_label=f"SimC (target) · {target.run_id}",
            header_caption=target.primary_model,
        ),
    ]
    scores_vs_a: list[float] = []
    scores_vs_b: list[float] = []
    rendered_any = False
    for agent_id in agent_ids:
        question_ids = sorted(
            {
                cell.cell_id.question_id
                for cell in cells
                if cell.cell_id.agent_id == agent_id and cell.cell_id.cutoff_round is None
            },
            key=natural_sort_key,
        )
        rows: list[GridRow] = []
        for question_id in question_ids:
            cell_a = cells_index.get((source_a.run_id, agent_id, question_id, None))
            cell_b = cells_index.get((source_b.run_id, agent_id, question_id, None))
            cell_c = cells_index.get((target.run_id, agent_id, question_id, None))
            if cell_a is None or cell_b is None or cell_c is None:
                continue
            score_vs_a = _cross_cell_similarity(
                replicas_a=cell_a.replicas, replicas_b=cell_c.replicas
            )
            score_vs_b = _cross_cell_similarity(
                replicas_a=cell_b.replicas, replicas_b=cell_c.replicas
            )
            if score_vs_a is None or score_vs_b is None:
                continue
            row_score = min(score_vs_a, score_vs_b)
            cells_by_column_key = {
                "sim_a": GridCell(replicas=cell_a.replicas, score=None, score_label="", extra=None),
                "sim_b": GridCell(replicas=cell_b.replicas, score=None, score_label="", extra=None),
                "sim_c": GridCell(
                    replicas=cell_c.replicas,
                    score=score_vs_a,
                    score_label="vs SimA",
                    extra=(score_vs_b, "vs SimB"),
                ),
            }
            rows.append(
                _build_question_row(
                    scenario_name=target.scenario_name,
                    question_id=question_id,
                    cells_by_column_key=cells_by_column_key,
                    row_score=row_score,
                    row_score_label="min sim",
                )
            )
            scores_vs_a.append(score_vs_a)
            scores_vs_b.append(score_vs_b)
        if not rows:
            continue
        rows.sort(key=lambda row: natural_sort_key(row.row_key))
        if not rendered_any:
            st.markdown(f"### {section_title}")
            st.markdown(section_explanation)
            rendered_any = True
        st.markdown(f"#### {agent_id}")
        _render_text_grid(columns=columns, rows=rows)
    return _CrossTeamSectionScores(vs_a=scores_vs_a, vs_b=scores_vs_b)


def _render_cross_team_subtab(
    probe_runs: list[ProbeSimilarityRun],
    evaluated: list[EvaluatedRun],
) -> None:
    """For one cross-team run, render imported-agent and co-actor comparisons."""
    _render_subtab_help(title="Cross-team swap", body=_CROSS_TEAM_HELP_BODY)
    cross_swap_runs = list_cross_swap_runs(evaluated_runs=evaluated)
    probe_runs_by_id = {run.run_id: run for run in probe_runs}
    eligible = [run for run in cross_swap_runs if probe_runs_by_id.get(run.run_id) is not None]
    if not eligible:
        st.info(
            "No cross-team runs with probe data available. "
            "Run `schmidt evaluate ... --metrics protocol_probe` on the "
            "cross-team target run first."
        )
        return
    options = {
        (
            f"{run.run_id} · imported {run.imported_model} @ R{run.round_start}"
            f" · A={run.source_a_run_id} · B={run.source_b_run_id}"
        ): run
        for run in eligible
    }
    chosen_label = st.selectbox(
        label="Cross-team run",
        options=list(options.keys()),
        index=0,
        key="probe_cross_team_run",
    )
    selected_cross_swap = options[chosen_label]
    target_run = probe_runs_by_id[selected_cross_swap.run_id]
    if not target_run.rows:
        st.warning(f"Target run {target_run.run_id} has no probe rows.")
        return
    context = _resolve_cross_team_context(
        target_run=target_run,
        target_run_dir=selected_cross_swap.run_dir,
        source_a_run_id=selected_cross_swap.source_a_run_id,
        source_b_run_id=selected_cross_swap.source_b_run_id,
        round_start=selected_cross_swap.round_start,
        probe_runs_by_id=probe_runs_by_id,
    )
    if context is None:
        return
    frontend_base = render_frontend_base(streamlit_key="probe_cross_team_frontend_base")
    target_url = run_url(frontend_base=frontend_base, run_id=context.target.run_id)
    source_a_url = run_url(frontend_base=frontend_base, run_id=context.source_a.run_id)
    source_b_url = run_url(frontend_base=frontend_base, run_id=context.source_b.run_id)
    st.markdown(
        f"[Open target ↗]({target_url}) · [Open source A ↗]({source_a_url})"
        f" · [Open source B ↗]({source_b_url})"
    )
    st.markdown(
        f"**Swap @ round {context.round_start}** · imported agent "
        f"`{context.replaced_agent_id}` arrived from `{context.source_b.run_id}` "
        f"into `{context.source_a.run_id}`."
    )
    st.markdown(_CROSS_TEAM_OVERVIEW_PROSE)
    target_agent_ids = sorted(_agents_in_run(run=context.target))
    imported_agent_ids = [
        agent_id for agent_id in target_agent_ids if agent_id == context.replaced_agent_id
    ]
    co_acting_agent_ids = [
        agent_id for agent_id in target_agent_ids if agent_id != context.replaced_agent_id
    ]
    imported_scores = _render_cross_team_grid(
        target=context.target,
        source_a=context.source_a,
        source_b=context.source_b,
        agent_ids=imported_agent_ids,
        section_title="Imported agent — protocol across SimA, SimB, SimC",
        section_explanation=_CROSS_TEAM_IMPORTED_PROSE.format(
            replaced_agent_id=context.replaced_agent_id,
            source_b_run_id=context.source_b.run_id,
            source_a_run_id=context.source_a.run_id,
        ),
    )
    co_actor_scores = _render_cross_team_grid(
        target=context.target,
        source_a=context.source_a,
        source_b=context.source_b,
        agent_ids=co_acting_agent_ids,
        section_title="Co-acting agents — protocol across SimA, SimB, SimC",
        section_explanation=_CROSS_TEAM_CO_ACTORS_PROSE.format(
            replaced_agent_id=context.replaced_agent_id,
            source_a_run_id=context.source_a.run_id,
            source_b_run_id=context.source_b.run_id,
        ),
    )
    _render_cross_team_summary(imported=imported_scores, co_actor=co_actor_scores)


def _render_cross_team_summary(
    *,
    imported: _CrossTeamSectionScores,
    co_actor: _CrossTeamSectionScores,
) -> None:
    """Render the bottom-of-tab summary tiles for both sections × both deltas."""
    if not (imported.vs_a or imported.vs_b or co_actor.vs_a or co_actor.vs_b):
        return
    st.markdown("---")
    tile_specs: list[tuple[str, list[float]]] = [
        ("Imported · median vs SimA", imported.vs_a),
        ("Imported · median vs SimB", imported.vs_b),
        ("Co-acting · median vs SimA", co_actor.vs_a),
        ("Co-acting · median vs SimB", co_actor.vs_b),
    ]
    summary_cols = st.columns(len(tile_specs))
    for column, (label, values) in zip(summary_cols, tile_specs, strict=True):
        if not values:
            column.metric(label=label, value="—")
            continue
        value_text, delta_text = _format_median_mean(values=values)
        column.metric(
            label=label,
            value=value_text,
            delta=delta_text,
            delta_color="off",
        )


# ---- Top-level entry point --------------------------------------------------


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the four-subtab Probe similarity view."""
    run_filter = seed_mode_filter.render_filters(key_prefix="probe_similarity")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    probe_runs = list_probe_similarity_runs(evaluated_runs=evaluated)
    if not probe_runs:
        st.info(
            "No runs have probe data. Run " "`schmidt evaluate ... --metrics protocol_probe` first."
        )
        return
    multi_swap_runs = list_multi_swap_runs(evaluated_runs=evaluated)
    (
        cross_team_panel,
        multi_swap_panel,
        compare_runs_panel,
        replica_self_panel,
    ) = st.tabs(
        [
            "Cross-team swap",
            "Multi-stage swap",
            "Compare runs",
            "Replica self-similarity",
        ]
    )
    with cross_team_panel:
        _render_cross_team_subtab(probe_runs=probe_runs, evaluated=evaluated)
    with multi_swap_panel:
        _render_multi_swap_subtab(probe_runs=probe_runs, multi_swap_runs=multi_swap_runs)
    with compare_runs_panel:
        _render_compare_runs_subtab(probe_runs=probe_runs)
    with replica_self_panel:
        _render_replica_self_subtab(probe_runs=probe_runs)
