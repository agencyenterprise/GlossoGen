"""Per-phase round-success comparison between a source run and its resume replicas.

Used by the Resume tab's *Multi-swap* subtab. Picks a source run, fetches its
``MultiSwapRun.phases`` plus the phases of every resume replica targeting that
source, and renders a grouped bar chart (source bar + replica-mean bar with
replica dots overlaid) plus a comparison table aligned by phase label.

The source's own phases are read via
:func:`analysis.results_viewer.multi_swap_data.build_multi_swap_run`; replicas
come from the evaluated catalog already loaded by the caller.
"""

from typing import Literal, NamedTuple

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.message_similarity import (
    SimilarityScoreFn,
    bigram_jaccard_score,
    levenshtein_score,
    mean_similarity_to_pool,
    phase_round_texts,
    pool_self_similarity,
    similarity_to_reference,
)
from analysis.results_viewer.multi_swap_data import MultiSwapRun, PhaseScore, build_multi_swap_run
from analysis.results_viewer.resume_data import ResumeRun
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, run_url
from analysis.results_viewer.series_plot import render_horizontal_checkboxes

_SOURCE_COLOR = "#0EA5E9"
_REPLICA_MEAN_COLOR = "#A855F7"
_REPLICA_DOT_COLOR = "#7E22CE"

ViewMode = Literal["round_success", "message_similarity", "ngram_overlap"]

_MODE_ROUND_SUCCESS: ViewMode = "round_success"
_MODE_MESSAGE_SIMILARITY: ViewMode = "message_similarity"
_MODE_NGRAM_OVERLAP: ViewMode = "ngram_overlap"

_SIMILARITY_MODES: frozenset[ViewMode] = frozenset({_MODE_MESSAGE_SIMILARITY, _MODE_NGRAM_OVERLAP})

_SCORE_FN_BY_MODE: dict[ViewMode, SimilarityScoreFn] = {
    _MODE_MESSAGE_SIMILARITY: levenshtein_score,
    _MODE_NGRAM_OVERLAP: bigram_jaccard_score,
}


def _is_similarity_mode(mode: ViewMode) -> bool:
    """Return ``True`` for any of the link-text similarity modes (Levenshtein, Jaccard, …)."""
    return mode in _SIMILARITY_MODES


def _score_fn_for(mode: ViewMode) -> SimilarityScoreFn:
    """Look up the per-pair score function for one of the similarity modes."""
    return _SCORE_FN_BY_MODE[mode]


class _MetricOption(NamedTuple):
    """One entry in the metric radio: ``ViewMode`` + display label + popover body."""

    mode: ViewMode
    display_name: str
    description: str


_METRIC_OPTIONS: list[_MetricOption] = [
    _MetricOption(
        mode=_MODE_ROUND_SUCCESS,
        display_name="Round success",
        description=(
            "**Round success** — fraction of phase rounds the judge marked stabilized.\n\n"
            "Source bar vs replica-mean bar per phase, with each replica's score overlaid "
            "as a dot. Phase A is shown (the cloned source rounds carry real outcomes)."
        ),
    ),
    _MetricOption(
        mode=_MODE_MESSAGE_SIMILARITY,
        display_name="Message similarity (Levenshtein)",
        description=(
            "**Message similarity** — per round inside the phase, "
            "`Levenshtein.normalized_similarity` of the concatenated link-channel messages, "
            "averaged across rounds.\n\n"
            "Edit-distance based: sensitive to message length and retry-count divergence. "
            "A replica that runs extra retry exchanges in a round scores low even when the "
            "shorthand vocabulary is identical to the source.\n\n"
            "Rounds with empty link text on either side are skipped. Phase A is excluded "
            "(replicas inherit it verbatim from the source clone)."
        ),
    ),
    _MetricOption(
        mode=_MODE_NGRAM_OVERLAP,
        display_name="N-gram overlap (word bigrams, Jaccard)",
        description=(
            "**N-gram overlap** — per round inside the phase, Jaccard similarity over "
            "word-level bigrams `(token_i, token_{i+1})`: `|A ∩ B| / |A ∪ B|` where A, B "
            "are the lowercased bigram sets of the concatenated link text. Averaged across "
            "rounds.\n\n"
            "Set-based: mostly insensitive to transcript length, so it isolates shared "
            "vocabulary / phrasing from retry-loop divergence. Complements Levenshtein for "
            "diagnosing 'is the protocol the same?' vs. 'is the transcript trajectory the "
            "same?'.\n\n"
            "Rounds with empty link text on either side are skipped. Phase A is excluded."
        ),
    ),
]


def _metric_option_for(mode: ViewMode) -> _MetricOption:
    """Look up the radio entry for a ``ViewMode``."""
    for option in _METRIC_OPTIONS:
        if option.mode == mode:
            return option
    raise KeyError(mode)


def _mode_from_display_name(name: str) -> ViewMode:
    """Map the user-facing radio label back to its ``ViewMode`` literal."""
    for option in _METRIC_OPTIONS:
        if option.display_name == name:
            return option.mode
    return _MODE_ROUND_SUCCESS


class _ReplicaPhaseScore(NamedTuple):
    """A single replica's outcome on one aligned phase."""

    run_id: str
    won: int
    total: int
    score: float
    url: str


class _AlignedPhase(NamedTuple):
    """One phase row aligned between source and N replicas.

    ``replica_scores`` is a parallel list of per-replica outcomes; entries are
    ``None`` when a replica did not reach that phase (e.g. ran out of rounds).
    """

    phase_index: int
    label: str
    round_start: int
    round_end: int
    swap_label: str
    source_score: PhaseScore
    replica_scores: list[_ReplicaPhaseScore | None]


def _format_swap_label(phase: PhaseScore, source_run: MultiSwapRun) -> str:
    """One-line description of the swap that opens ``phase``."""
    if phase.swap is None:
        agent_models = ", ".join(
            f"{agent_id}={model}"
            for agent_id, model in sorted(source_run.initial_agent_models.items())
        )
        return f"initial: {agent_models}"
    return f"swap {phase.swap.agent_id} → {phase.swap.new_model} @ r{phase.swap.round_number}"


def _align_phases(
    source_run: MultiSwapRun,
    replica_runs: list[MultiSwapRun],
    frontend_base: str,
    mode: ViewMode,
) -> list[_AlignedPhase]:
    """Match each source phase with the same phase in every replica.

    Alignment is positional by ``phase_index``: source phase 0 ↔ replica phase
    0, etc. ``scheduled_events`` is inherited from the source on resume, so
    replicas have the same swap boundaries and the same phase structure.

    ``mode`` controls what each cell's ``score`` field carries:

    - ``round_success``: ``replica_phase.score`` (fraction of phase rounds
      stabilized) and ``source_score`` is the source's matching ``PhaseScore``.
    - ``message_similarity`` / ``ngram_overlap``: the mean per-round similarity
      to the source under the matching score function (Levenshtein or word-
      bigram Jaccard). Source self-similarity = 1.0 by construction. Replicas
      with no link text inside the phase window are skipped.
    """
    is_similarity = _is_similarity_mode(mode=mode)
    score_fn = _score_fn_for(mode=mode) if is_similarity else None
    aligned: list[_AlignedPhase] = []
    for src_phase in source_run.phases:
        # Phase A (pre-first-swap) is inherited verbatim from the source via
        # the JSONL clone in similarity modes → every replica's link text equals
        # the source's text → similarity ≡ 1.0. Skip it to keep the chart
        # informative. Round-success mode still renders Phase A because the
        # cloned source rounds carry real round_success outcomes.
        if is_similarity and src_phase.swap is None:
            continue
        replica_scores: list[_ReplicaPhaseScore | None] = []
        for replica in replica_runs:
            replica_phase = next(
                (p for p in replica.phases if p.phase_index == src_phase.phase_index),
                None,
            )
            if replica_phase is None or replica_phase.total == 0:
                replica_scores.append(None)
                continue
            if is_similarity and score_fn is not None:
                similarity = similarity_to_reference(
                    run=replica,
                    reference_run=source_run,
                    phase_index=src_phase.phase_index,
                    score_fn=score_fn,
                )
                if similarity is None:
                    replica_scores.append(None)
                    continue
                replica_scores.append(
                    _ReplicaPhaseScore(
                        run_id=replica.run_id,
                        won=0,
                        total=0,
                        score=similarity,
                        url=run_url(frontend_base=frontend_base, run_id=replica.run_id),
                    )
                )
                continue
            replica_scores.append(
                _ReplicaPhaseScore(
                    run_id=replica.run_id,
                    won=replica_phase.won,
                    total=replica_phase.total,
                    score=replica_phase.score,
                    url=run_url(frontend_base=frontend_base, run_id=replica.run_id),
                )
            )
        if is_similarity:
            display_source = src_phase._replace(score=1.0, won=0, total=0)
        else:
            display_source = src_phase
        aligned.append(
            _AlignedPhase(
                phase_index=src_phase.phase_index,
                label=src_phase.label,
                round_start=src_phase.round_start,
                round_end=src_phase.round_end,
                swap_label=_format_swap_label(phase=src_phase, source_run=source_run),
                source_score=display_source,
                replica_scores=replica_scores,
            )
        )
    return aligned


def _replica_mean(scores: list[_ReplicaPhaseScore | None]) -> float | None:
    """Mean replica score for one phase, or ``None`` when no replicas reached it."""
    values = [s.score for s in scores if s is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _build_comparison_chart(aligned: list[_AlignedPhase], mode: ViewMode) -> go.Figure:
    """Source bar + replica-mean bar grouped per phase, with replica dots overlaid.

    The source bar is suppressed in any similarity mode because the source-vs-
    source similarity is trivially 1.0 on every phase and adds noise to the
    chart.
    """
    is_similarity = _is_similarity_mode(mode=mode)
    labels = [p.label for p in aligned]
    replica_mean_y: list[float] = []
    replica_mean_text: list[str] = []
    for p in aligned:
        mean = _replica_mean(scores=p.replica_scores)
        if mean is None:
            replica_mean_y.append(0.0)
            replica_mean_text.append("—")
            continue
        replica_mean_y.append(mean)
        present = [s for s in p.replica_scores if s is not None]
        replica_mean_text.append(f"mean of {len(present)}<br>({round(mean * 100)}%)")

    fig = go.Figure()
    if not is_similarity:
        source_y = [p.source_score.score for p in aligned]
        source_text = [
            f"{p.source_score.won}/{p.source_score.total}<br>"
            f"({round(p.source_score.score * 100)}%)"
            for p in aligned
        ]
        fig.add_trace(
            go.Bar(
                x=labels,
                y=source_y,
                text=source_text,
                textposition="inside",
                marker_color=_SOURCE_COLOR,
                name="Source",
                hovertemplate="Source · %{x}<br>%{text}<extra></extra>",
            )
        )
    replica_legend = "Replicas (mean similarity to source)" if is_similarity else "Replicas (mean)"
    fig.add_trace(
        go.Bar(
            x=labels,
            y=replica_mean_y,
            text=replica_mean_text,
            textposition="inside",
            marker_color=_REPLICA_MEAN_COLOR,
            name=replica_legend,
            hovertemplate="Replicas · %{x}<br>%{text}<extra></extra>",
        )
    )
    # Replica dots overlay so individual replica scores are visible alongside the mean bar.
    dot_x: list[str] = []
    dot_y: list[float] = []
    dot_hover: list[str] = []
    dot_urls: list[str] = []
    for p in aligned:
        for replica in p.replica_scores:
            if replica is None:
                continue
            dot_x.append(p.label)
            dot_y.append(replica.score)
            if is_similarity:
                hover_body = f"similarity to source: {round(replica.score * 100)}%"
            else:
                hover_body = f"{replica.won}/{replica.total} ({round(replica.score * 100)}%)"
            dot_hover.append(
                f"{replica.run_id}<br>{p.label}<br>{hover_body}<br>click to open · {replica.url}"
            )
            dot_urls.append(replica.url)
    if dot_x:
        fig.add_trace(
            go.Scatter(
                x=dot_x,
                y=dot_y,
                mode="markers",
                marker=dict(color=_REPLICA_DOT_COLOR, size=10, line=dict(color="white", width=1)),
                name="Replica",
                hovertext=dot_hover,
                hoverinfo="text",
                customdata=dot_urls,
                xaxis="x2",
            )
        )
    if mode == _MODE_MESSAGE_SIMILARITY:
        y_title = "Normalized Levenshtein similarity to source (link-channel text, per phase)"
    elif mode == _MODE_NGRAM_OVERLAP:
        y_title = "Word-bigram Jaccard overlap with source (link-channel text, per phase)"
    else:
        y_title = "Fraction of phase rounds stabilized"
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Phase"),
        xaxis2=dict(overlaying="x", showticklabels=False, showgrid=False),
        yaxis=dict(
            title=y_title,
            range=[0.0, 1.05],
            tickformat=".0%",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=60, b=60),
        height=460,
    )
    return fig


_MAX_SAMPLE_CHARS = 160


def _truncate(text: str, max_chars: int = _MAX_SAMPLE_CHARS) -> str:
    """Single-line truncation: collapse newlines, trim, append ``…`` when over-length."""
    flat = " ⏎ ".join(text.split("\n"))
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1] + "…"


def _sample_round_numbers(phase: _AlignedPhase, per_phase: int = 3) -> list[int]:
    """Pick ``per_phase`` representative round numbers spread across the phase window.

    Always picks the first and last rounds; fills middle slots evenly. Falls
    back to all available rounds when the phase window is shorter than
    ``per_phase``.
    """
    rounds = list(range(phase.round_start, phase.round_end + 1))
    if len(rounds) <= per_phase:
        return rounds
    if per_phase == 1:
        return [rounds[len(rounds) // 2]]
    step = (len(rounds) - 1) / (per_phase - 1)
    return [rounds[round(i * step)] for i in range(per_phase)]


_SCORE_LABEL_BY_MODE: dict[ViewMode, str] = {
    _MODE_MESSAGE_SIMILARITY: "Levenshtein similarity",
    _MODE_NGRAM_OVERLAP: "Word-bigram Jaccard",
}

_SCORE_FORMULA_BY_MODE: dict[ViewMode, str] = {
    _MODE_MESSAGE_SIMILARITY: "`Levenshtein.normalized_similarity(source_text, replica_text)`",
    _MODE_NGRAM_OVERLAP: (
        "`|A ∩ B| / |A ∪ B|` where A, B are the word-bigram sets of "
        "`source_text` and `replica_text`"
    ),
}


def _render_round_message_samples(
    aligned: list[_AlignedPhase],
    source_run: MultiSwapRun,
    replica_runs: list[MultiSwapRun],
    mode: ViewMode,
    frontend_base: str,
) -> None:
    """Per-round text samples + per-round similarity for sanity-checking.

    Rendered as an expander below the comparison table when the view mode is a
    similarity mode. For every aligned phase, picks 3 representative rounds
    (first / middle / last) and shows one row per (round, replica) with the
    source's truncated text, the replica's truncated text, and the single-pair
    score under the chosen ``mode`` (Levenshtein or word-bigram Jaccard). Lets
    the user eyeball whether the phase-averaged similarity numbers are
    reasonable.

    The replica column carries the replica's frontend URL and is rendered as a
    clickable link via ``st.column_config.LinkColumn``.
    """
    if not aligned:
        return
    score_fn = _score_fn_for(mode=mode)
    score_label = _SCORE_LABEL_BY_MODE[mode]
    score_formula = _SCORE_FORMULA_BY_MODE[mode]
    source_url = run_url(frontend_base=frontend_base, run_id=source_run.run_id)
    rows: list[dict[str, str]] = []
    for phase in aligned:
        source_texts = phase_round_texts(run=source_run, phase_index=phase.phase_index)
        sample_rounds = _sample_round_numbers(phase=phase)
        for round_number in sample_rounds:
            source_text = source_texts.get(round_number, "")
            for replica in replica_runs:
                replica_texts = phase_round_texts(run=replica, phase_index=phase.phase_index)
                replica_text = replica_texts.get(round_number, "")
                sim = score_fn(source_text, replica_text)
                rows.append(
                    {
                        "Phase": phase.label,
                        "Round": str(round_number),
                        "Replica": run_url(frontend_base=frontend_base, run_id=replica.run_id),
                        "Source text": _truncate(text=source_text) if source_text else "—",
                        "Replica text": _truncate(text=replica_text) if replica_text else "—",
                        "Per-round sim": "—" if sim is None else f"{round(sim * 100)}%",
                    }
                )
    if not rows:
        return
    with st.expander(
        f"Per-round message samples — first/mid/last round of each phase × "
        f"{len(replica_runs)} baseline replica(s) — source: {source_run.run_id} "
        f"([open]({source_url}))",
        expanded=False,
    ):
        st.caption(
            f"One row per (sampled round × replica). 'Per-round sim' is **{score_label}**: "
            f"{score_formula}, computed on the concatenated link-channel messages of that "
            "round on each side. The phase-level similarity number plotted above is the "
            f"mean of these per-round values across the whole phase. Texts truncated to "
            f"{_MAX_SAMPLE_CHARS} chars; `⏎` marks a newline. Click any Replica cell to "
            "open that run."
        )
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "Replica": st.column_config.LinkColumn(
                    "Replica",
                    help="Click to open the replica run in the frontend.",
                    display_text=r"runs/[^/]+/(\d+)$",
                ),
            },
        )


def _replica_id_per_column(aligned: list[_AlignedPhase]) -> list[tuple[str, str] | None]:
    """Discover ``(run_id, url)`` per column position across all aligned phases.

    A replica column index has a stable identity (same replica across every
    phase) but any single phase might have a ``None`` cell for that column if
    that replica didn't reach the phase. Walks all phases to find the first
    non-``None`` cell per column and returns its run_id/url.
    """
    if not aligned:
        return []
    replica_count = len(aligned[0].replica_scores)
    out: list[tuple[str, str] | None] = []
    for index in range(replica_count):
        first: tuple[str, str] | None = None
        for phase in aligned:
            cell = phase.replica_scores[index]
            if cell is not None:
                first = (cell.run_id, cell.url)
                break
        out.append(first)
    return out


def _render_comparison_table(
    aligned: list[_AlignedPhase],
    mode: ViewMode,
    source_run: MultiSwapRun,
    frontend_base: str,
) -> None:
    """Comparison table with one row per phase: source vs each replica.

    Rendered as a markdown table so the source + replica run IDs in the column
    headers can be hyperlinks back to the frontend. Each header reads
    ``Source ([1778162284](url))`` / ``Rep 1 ([1779359865](url))`` so a click
    opens the run.
    """
    if not aligned:
        return
    is_similarity = _is_similarity_mode(mode=mode)
    replica_count = len(aligned[0].replica_scores)
    replica_ids = _replica_id_per_column(aligned=aligned)
    source_url = run_url(frontend_base=frontend_base, run_id=source_run.run_id)

    headers = [
        "Phase",
        "Rounds",
        "Boundary",
        f"Source ([{source_run.run_id}]({source_url}))",
    ]
    for index in range(replica_count):
        info = replica_ids[index]
        if info is None:
            headers.append(f"Rep {index + 1}")
            continue
        run_id, url = info
        headers.append(f"Rep {index + 1} ([{run_id}]({url}))")
    headers.append("Replica mean")

    rows: list[list[str]] = []
    for phase in aligned:
        if is_similarity:
            source_cell = "self-sim = 100%"
        else:
            source_cell = (
                f"{phase.source_score.won}/{phase.source_score.total} "
                f"({round(phase.source_score.score * 100)}%)"
            )
        row: list[str] = [
            phase.label,
            f"{phase.round_start}-{phase.round_end}",
            phase.swap_label,
            source_cell,
        ]
        for index in range(replica_count):
            replica = phase.replica_scores[index]
            if replica is None:
                row.append("—")
                continue
            if is_similarity:
                row.append(f"{round(replica.score * 100)}%")
            else:
                row.append(f"{replica.won}/{replica.total} ({round(replica.score * 100)}%)")
        mean = _replica_mean(scores=phase.replica_scores)
        row.append("—" if mean is None else f"{round(mean * 100)}%")
        rows.append(row)

    st.markdown(_build_markdown_table(headers=headers, rows=rows), unsafe_allow_html=False)


def _build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Serialize ``rows`` (parallel to ``headers``) as a Github-flavored markdown table.

    Pipe (``|``) characters inside cells are escaped (``\\|``) so they do not
    break the column structure. Newlines inside cells are collapsed to ``<br>``.
    """

    def _escape(cell: str) -> str:
        return cell.replace("|", "\\|").replace("\n", "<br>")

    lines: list[str] = []
    lines.append("| " + " | ".join(_escape(h) for h in headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_escape(cell) for cell in row) + " |")
    return "\n".join(lines)


_OVERVIEW_PALETTE = [
    "#0EA5E9",  # sky
    "#A855F7",  # violet
    "#F97316",  # orange
    "#10B981",  # emerald
    "#EF4444",  # red
    "#EAB308",  # yellow
]

_NO_BUDGET_LABEL = "no budget tag"

_INTERVENTION_LABELS: frozenset[str] = frozenset(
    {
        "budget_increased",
        "budget_decreased",
        "with_noise",
        "postmortem_kept_on",
        "new_motifs_injected",
    }
)
_BASELINE_INTERVENTION_LABEL = "baseline"


def _extract_budget_label(labels: list[str]) -> str:
    """Return the ``budget=*`` label from ``labels`` or a sentinel string.

    Replicas tag their variant budget with ``budget=<N>`` (e.g. ``budget=450``,
    ``budget=1500``). Runs missing the tag are bucketed under a single sentinel
    so they remain filterable rather than silently dropped.
    """
    for label in labels:
        if label.startswith("budget="):
            return label
    return _NO_BUDGET_LABEL


def _extract_intervention_label(labels: list[str]) -> str:
    """Return the experiment-intervention label from ``labels``, or ``baseline``.

    Replicas tag their pressure intervention with one of ``budget_increased``,
    ``budget_decreased``, ``with_noise``, ``postmortem_kept_on``, or
    ``new_motifs_injected``. Replicas missing all of those are baselines (a
    plain resume with no knob overrides) and bucket under ``baseline`` so they
    remain filterable.
    """
    for label in labels:
        if label in _INTERVENTION_LABELS:
            return label
    return _BASELINE_INTERVENTION_LABEL


def _filter_resumes_by_budget(
    resumes_by_source: dict[str, list[ResumeRun]],
    selected_budgets: set[str],
) -> dict[str, list[ResumeRun]]:
    """Drop replicas whose budget label is not in ``selected_budgets``.

    Sources whose replicas all filter out are dropped from the returned mapping.
    """
    out: dict[str, list[ResumeRun]] = {}
    for source_id, resumes in resumes_by_source.items():
        kept = [r for r in resumes if _extract_budget_label(labels=r.labels) in selected_budgets]
        if kept:
            out[source_id] = kept
    return out


def _filter_resumes_by_intervention(
    resumes_by_source: dict[str, list[ResumeRun]],
    selected_interventions: set[str],
) -> dict[str, list[ResumeRun]]:
    """Drop replicas whose intervention label is not in ``selected_interventions``.

    Sources whose replicas all filter out are dropped from the returned mapping.
    """
    out: dict[str, list[ResumeRun]] = {}
    for source_id, resumes in resumes_by_source.items():
        kept = [
            r
            for r in resumes
            if _extract_intervention_label(labels=r.labels) in selected_interventions
        ]
        if kept:
            out[source_id] = kept
    return out


def _build_replica_runs_for_source(
    resumes: list[ResumeRun],
    evaluated_by_run_id: dict[str, EvaluatedRun],
) -> tuple[list[MultiSwapRun], list[str]]:
    """Return ``(replica_runs, skipped_run_ids)`` for one source's resumes.

    Each replica's ``MultiSwapRun`` is built via the public sync
    :func:`build_multi_swap_run`; the byte-level + in-memory caches inside
    that function keep repeat calls cheap.
    """
    replica_runs: list[MultiSwapRun] = []
    skipped: list[str] = []
    for resume in resumes:
        evaluated_run = evaluated_by_run_id.get(resume.run_id)
        if evaluated_run is None:
            skipped.append(resume.run_id)
            continue
        replica = build_multi_swap_run(evaluated=evaluated_run)
        if replica is None:
            skipped.append(resume.run_id)
            continue
        replica_runs.append(replica)
    return replica_runs, skipped


def _gather_sources_and_replicas(
    resumes_by_source: dict[str, list[ResumeRun]],
    evaluated_by_run_id: dict[str, EvaluatedRun],
) -> list[tuple[str, MultiSwapRun, list[MultiSwapRun]]]:
    """For every source with ≥1 evaluatable replica, return its source run + replica runs.

    Sources absent from the evaluated catalog, or whose source JSONL has no
    in-run swaps, are dropped silently — the overview chart's purpose is to
    summarise the population that has data on both sides.
    """
    out: list[tuple[str, MultiSwapRun, list[MultiSwapRun]]] = []
    for source_id, resumes in sorted(resumes_by_source.items()):
        source_evaluated = evaluated_by_run_id.get(source_id)
        if source_evaluated is None:
            continue
        source_run = build_multi_swap_run(evaluated=source_evaluated)
        if source_run is None:
            continue
        replica_runs, _ = _build_replica_runs_for_source(
            resumes=resumes,
            evaluated_by_run_id=evaluated_by_run_id,
        )
        if not replica_runs:
            continue
        out.append((source_id, source_run, replica_runs))
    return out


class _ModelPhaseAggregate(NamedTuple):
    """Pooled per-(model, phase) scores aggregated across every source + replica.

    ``baseline_scores`` carries one entry per ``baseline``-tagged replica phase
    (the unmodified resume-at-round control: same source, same knobs).
    ``replica_scores`` carries one entry per **non-baseline** intervention
    replica phase that passed the user's filters. The chart plots
    ``mean(replica_scores) − mean(baseline_scores)`` per (model, phase).
    """

    model: str
    phase_index: int
    phase_label: str
    baseline_scores: list[float]
    replica_scores: list[float]


def _aggregate_by_model(
    sources_data: list[tuple[str, MultiSwapRun, list[MultiSwapRun]]],
    baseline_replicas_by_source: dict[str, list[MultiSwapRun]],
    mode: ViewMode,
) -> dict[tuple[str, int], _ModelPhaseAggregate]:
    """Pool per-phase scores by ``(primary_model, phase_index)``.

    For each source: every ``baseline``-tagged replica's phase score
    contributes to ``baseline_scores`` (the pooled control mean). For each
    non-baseline replica in ``sources_data``: every phase the replica reached
    contributes to ``replica_scores``. The grouping key is the source's
    ``primary_model``.

    Phases with ``swap is None`` (Phase A, the pre-first-swap window) are
    skipped entirely: replicas start *after* the first swap so the rounds in
    that window are inherited verbatim from the source via the JSONL clone
    and contain no resume-side activity — comparing them is meaningless.

    The reference is the **pooled baseline-replica mean**, not the single
    source trajectory, because a single source can land on a bad path (e.g.
    veyru/1778525576 ran into a +22 pp self-vs-source artifact) that would
    make every intervention look misleadingly good.
    """
    buckets: dict[tuple[str, int], _ModelPhaseAggregate] = {}

    def _bucket_for(model: str, phase_index: int, label: str) -> _ModelPhaseAggregate:
        key = (model, phase_index)
        existing = buckets.get(key)
        if existing is not None:
            return existing
        agg = _ModelPhaseAggregate(
            model=model,
            phase_index=phase_index,
            phase_label=label,
            baseline_scores=[],
            replica_scores=[],
        )
        buckets[key] = agg
        return agg

    is_similarity = _is_similarity_mode(mode=mode)
    score_fn = _score_fn_for(mode=mode) if is_similarity else None
    for source_id, source_run, replica_runs in sources_data:
        model = source_run.primary_model
        source_baselines = baseline_replicas_by_source.get(source_id, [])
        if is_similarity and score_fn is not None:
            # baseline_scores becomes pool-self-similarity per source (one entry per source);
            # replica_scores becomes each intervention replica's mean similarity to the pool.
            for src_phase in source_run.phases:
                if src_phase.swap is None:
                    continue
                agg = _bucket_for(
                    model=model, phase_index=src_phase.phase_index, label=src_phase.label
                )
                pool_self = pool_self_similarity(
                    pool=source_baselines,
                    phase_index=src_phase.phase_index,
                    score_fn=score_fn,
                )
                if pool_self is not None:
                    agg.baseline_scores.append(pool_self)
                for replica in replica_runs:
                    similarity = mean_similarity_to_pool(
                        run=replica,
                        pool=source_baselines,
                        phase_index=src_phase.phase_index,
                        score_fn=score_fn,
                    )
                    if similarity is not None:
                        agg.replica_scores.append(similarity)
            continue
        # round_success mode: replicate the original per-phase pooling.
        for baseline_replica in source_baselines:
            for bphase in baseline_replica.phases:
                if bphase.swap is None:
                    continue
                agg = _bucket_for(model=model, phase_index=bphase.phase_index, label=bphase.label)
                if bphase.total > 0:
                    agg.baseline_scores.append(bphase.score)
        for replica in replica_runs:
            for rphase in replica.phases:
                if rphase.swap is None:
                    continue
                agg = _bucket_for(model=model, phase_index=rphase.phase_index, label=rphase.label)
                if rphase.total > 0:
                    agg.replica_scores.append(rphase.score)
    return buckets


def _build_model_delta_chart(
    buckets: dict[tuple[str, int], _ModelPhaseAggregate],
    mode: ViewMode,
) -> go.Figure:
    """Δ pp per phase, one bar group per model.

    For ``mode='round_success'``: bar = mean(intervention round_success) −
    mean(baseline round_success). For ``mode='message_similarity'``: bar =
    mean(intervention-to-baseline-pool similarity) − baseline-self-similarity.
    A *negative* bar in similarity mode means the intervention diverges more
    from baseline language than baselines diverge from each other.
    """
    is_similarity = _is_similarity_mode(mode=mode)
    models = sorted({k[0] for k in buckets})
    phase_index_to_label: dict[int, str] = {}
    for (_, idx), agg in buckets.items():
        phase_index_to_label[idx] = agg.phase_label
    phase_indices = sorted(phase_index_to_label)
    phase_labels = [phase_index_to_label[idx] for idx in phase_indices]

    fig = go.Figure()
    for i, model in enumerate(models):
        color = _OVERVIEW_PALETTE[i % len(_OVERVIEW_PALETTE)]
        deltas: list[float | None] = []
        hover: list[str] = []
        text_labels: list[str] = []
        for phase_index in phase_indices:
            bucket = buckets.get((model, phase_index))
            if bucket is None or not bucket.baseline_scores or not bucket.replica_scores:
                deltas.append(None)
                hover.append(f"{model} · {phase_index_to_label[phase_index]}<br>no data")
                text_labels.append("")
                continue
            baseline_mean = sum(bucket.baseline_scores) / len(bucket.baseline_scores)
            replica_mean = sum(bucket.replica_scores) / len(bucket.replica_scores)
            delta_pp = (replica_mean - baseline_mean) * 100
            deltas.append(delta_pp)
            b_n = len(bucket.baseline_scores)
            r_n = len(bucket.replica_scores)
            if is_similarity:
                hover.append(
                    f"{model} · {bucket.phase_label}<br>"
                    f"baseline self-similarity: {round(baseline_mean * 100)}% (n={b_n} sources)<br>"
                    f"intervention→baseline: {round(replica_mean * 100)}% (n={r_n} replicas)<br>"
                    f"Δ = {delta_pp:+.1f} pp"
                )
            else:
                hover.append(
                    f"{model} · {bucket.phase_label}<br>"
                    f"baseline replicas: {round(baseline_mean * 100)}% (n={b_n})<br>"
                    f"intervention replicas: {round(replica_mean * 100)}% (n={r_n})<br>"
                    f"Δ = {delta_pp:+.1f} pp"
                )
            text_labels.append(f"{delta_pp:+.0f} pp")
        fig.add_trace(
            go.Bar(
                x=phase_labels,
                y=deltas,
                marker_color=color,
                text=text_labels,
                textposition="outside",
                name=model,
                hovertext=hover,
                hoverinfo="text",
            )
        )
    if mode == _MODE_MESSAGE_SIMILARITY:
        overview_y_title = "Δ Levenshtein(intervention→baseline) − Levenshtein(baseline self), pp"
    elif mode == _MODE_NGRAM_OVERLAP:
        overview_y_title = (
            "Δ bigram-Jaccard(intervention→baseline) − bigram-Jaccard(baseline self), pp"
        )
    else:
        overview_y_title = "Δ intervention-replica mean − baseline-replica mean (pp)"
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Phase"),
        yaxis=dict(
            title=overview_y_title,
            zeroline=True,
            zerolinecolor="#475569",
            zerolinewidth=2,
        ),
        legend=dict(
            title="Model",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        margin=dict(l=60, r=20, t=60, b=60),
        height=420,
    )
    return fig


def _render_model_delta_table(
    buckets: dict[tuple[str, int], _ModelPhaseAggregate],
) -> None:
    """One row per (model, phase): baseline mean, intervention mean, Δ pp, sample sizes."""
    rows: list[dict[str, str]] = []
    for (model, _), agg in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        baseline_mean = (
            sum(agg.baseline_scores) / len(agg.baseline_scores) if agg.baseline_scores else None
        )
        replica_mean = (
            sum(agg.replica_scores) / len(agg.replica_scores) if agg.replica_scores else None
        )
        if baseline_mean is None or replica_mean is None:
            delta = "—"
        else:
            delta = f"{(replica_mean - baseline_mean) * 100:+.1f} pp"
        rows.append(
            {
                "Model": model,
                "Phase": agg.phase_label,
                "Baseline replica mean": (
                    "—" if baseline_mean is None else f"{round(baseline_mean * 100)}%"
                ),
                "Baseline n": str(len(agg.baseline_scores)),
                "Intervention replica mean": (
                    "—" if replica_mean is None else f"{round(replica_mean * 100)}%"
                ),
                "Intervention n": str(len(agg.replica_scores)),
                "Δ (intervention − baseline)": delta,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _format_source_option(
    source_id: str,
    evaluated: EvaluatedRun | None,
    baseline_count: int,
) -> str:
    """Build the selectbox label: ``<id> · <model> · budget=<N> · K baseline replica(s)``.

    The per-source chart only consumes baseline replicas (no knob overrides),
    so the label surfaces just that count. Model + budget come from
    ``EvaluatedRun.metadata``.
    """
    parts = [source_id]
    if evaluated is not None:
        parts.append(evaluated.metadata.primary_model)
        raw_budget = evaluated.metadata.scenario_config.get("round_time_budget_seconds")
        if isinstance(raw_budget, (int, float)):
            parts.append(f"budget={int(raw_budget)}")
    parts.append(f"{baseline_count} baseline replica(s)")
    return " · ".join(parts)


def _pick_source(
    resumes_by_source: dict[str, list[ResumeRun]],
    evaluated_by_run_id: dict[str, EvaluatedRun],
    key_prefix: str,
) -> str | None:
    """Streamlit selectbox listing every source with at least one baseline resume.

    Sources whose resumes are all intervention replicas (no baseline control)
    are dropped from the dropdown since the per-source chart can't render
    anything for them. Each option's label carries ``primary_model``,
    ``round_time_budget_seconds``, and the baseline count.
    """
    options: list[str] = []
    baseline_counts: dict[str, int] = {}
    for source, resumes in sorted(resumes_by_source.items()):
        baseline_count = sum(
            1
            for r in resumes
            if _extract_intervention_label(labels=r.labels) == _BASELINE_INTERVENTION_LABEL
        )
        if baseline_count == 0:
            continue
        options.append(source)
        baseline_counts[source] = baseline_count
    if not options:
        return None
    formatted = [
        _format_source_option(
            source_id=source,
            evaluated=evaluated_by_run_id.get(source),
            baseline_count=baseline_counts[source],
        )
        for source in options
    ]
    chosen_index = st.selectbox(
        label="Source run",
        options=range(len(options)),
        format_func=lambda i: formatted[i],
        key=f"{key_prefix}_source_picker",
    )
    return options[chosen_index]


def render(
    multi_swap_resumes: list[ResumeRun],
    evaluated: list[EvaluatedRun],
    frontend_base: str,
    key_prefix: str,
) -> None:
    """Render the Multi-swap subtab body: per-phase source-vs-replicas comparison."""
    if not multi_swap_resumes:
        st.info("No resume runs with in-run agent swaps in this scenario.")
        return
    resumes_by_source: dict[str, list[ResumeRun]] = {}
    for resume in multi_swap_resumes:
        resumes_by_source.setdefault(resume.source_run_id, []).append(resume)
    evaluated_by_run_id = {run.run_id: run for run in evaluated}
    chosen_source = _pick_source(
        resumes_by_source=resumes_by_source,
        evaluated_by_run_id=evaluated_by_run_id,
        key_prefix=key_prefix,
    )
    if chosen_source is None:
        return
    source_evaluated = evaluated_by_run_id.get(chosen_source)
    if source_evaluated is None:
        st.warning(
            f"Source run `{chosen_source}` is not in the evaluated catalog. "
            "Run `schmidt evaluate` on it so its phase scores can be loaded."
        )
        return
    source_run = build_multi_swap_run(evaluated=source_evaluated)
    if source_run is None:
        st.warning(
            f"Source run `{chosen_source}` has no in-run agent swaps; its replicas "
            "would not have any either."
        )
        return
    # Per-source view shows only *baseline* replicas (no intervention knob overrides).
    # Intervention replicas live in the overview chart below where the
    # intervention filter cycles between them. Including interventions here
    # would blur the source-vs-control comparison the chart is built for.
    baseline_resumes = [
        r
        for r in resumes_by_source[chosen_source]
        if _extract_intervention_label(labels=r.labels) == _BASELINE_INTERVENTION_LABEL
    ]
    replica_runs, missing = _build_replica_runs_for_source(
        resumes=baseline_resumes,
        evaluated_by_run_id=evaluated_by_run_id,
    )
    if missing:
        st.caption(
            f"Skipped {len(missing)} baseline replica(s) without a usable evaluation: "
            f"{', '.join(missing)}"
        )
    if not replica_runs:
        st.info(
            "No evaluated **baseline** replicas (no knob overrides) for the chosen source. "
            "Run `schmidt evaluate` on its baseline resume runs so their phase scores load."
        )
        return
    display_names = [opt.display_name for opt in _METRIC_OPTIONS]
    radio_col, info_col = st.columns([8, 1])
    with radio_col:
        mode_choice = st.radio(
            "Metric",
            options=display_names,
            index=0,
            horizontal=True,
            key=f"{key_prefix}_metric_mode",
        )
    mode: ViewMode = _mode_from_display_name(name=mode_choice)
    selected_option = _metric_option_for(mode=mode)
    with info_col:
        st.markdown("&nbsp;")
        with st.popover("ⓘ", help="How this metric is computed"):
            st.markdown(selected_option.description)
    aligned = _align_phases(
        source_run=source_run,
        replica_runs=replica_runs,
        frontend_base=frontend_base,
        mode=mode,
    )
    if mode == _MODE_MESSAGE_SIMILARITY:
        st.caption(
            "Each replica's bar/dot shows the **mean per-round Levenshtein similarity** "
            "to the source's link-channel text within the phase. Per round: similarity of "
            "the concatenated link text on each side; rounds with empty text on either "
            "side are skipped. Phase score = arithmetic mean of surviving per-round sims. "
            "100% = identical per round, 0% = completely different."
        )
    elif mode == _MODE_NGRAM_OVERLAP:
        st.caption(
            "Each replica's bar/dot shows the **mean per-round word-bigram Jaccard "
            "overlap** with the source's link-channel text within the phase. Per round: "
            "`|A ∩ B| / |A ∪ B|` where A, B are the lowercased word-bigram sets of the "
            "concatenated link text on each side. Phase score = arithmetic mean of "
            "surviving per-round overlaps. Mostly insensitive to transcript length, so "
            "a long retry-heavy round still scores high if both sides reuse the same "
            "vocabulary."
        )
    else:
        st.caption(
            "Source bar vs replica-mean bar per phase, with each replica's score "
            "overlaid as a dot."
        )
    fig = _build_comparison_chart(aligned=aligned, mode=mode)
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode=("points",),
        key=f"{key_prefix}_phase_comparison_chart_{mode}",
    )
    maybe_open_clicked_run(
        chart_event=chart_event,
        session_key=f"{key_prefix}_multi_swap_last_opened_url",
    )
    _render_comparison_table(
        aligned=aligned,
        mode=mode,
        source_run=source_run,
        frontend_base=frontend_base,
    )
    if _is_similarity_mode(mode=mode):
        _render_round_message_samples(
            aligned=aligned,
            source_run=source_run,
            replica_runs=replica_runs,
            mode=mode,
            frontend_base=frontend_base,
        )

    st.markdown("---")
    st.subheader("Overview — Δ intervention vs baseline replicas, grouped by model")
    if mode == _MODE_MESSAGE_SIMILARITY:
        st.caption(
            "Metric: **Levenshtein similarity** (link channel). For each (model, phase): "
            "bar = mean( intervention replica's similarity to the baseline-replica pool ) − "
            "mean pairwise similarity within the baseline-replica pool ('how similar are "
            "baselines to each other?'). A **negative** bar means the intervention diverges "
            "from baseline language more than baselines diverge from each other. Phase A is "
            "excluded (replicas inherit it verbatim from the source clone)."
        )
    elif mode == _MODE_NGRAM_OVERLAP:
        st.caption(
            "Metric: **word-bigram Jaccard overlap** (link channel). For each (model, "
            "phase): bar = mean( intervention replica's bigram overlap with the baseline-"
            "replica pool ) − mean pairwise bigram overlap within the baseline-replica "
            "pool. A **negative** bar means the intervention's vocabulary/phrasing diverges "
            "from baseline more than baselines diverge from each other. Phase A is "
            "excluded."
        )
    else:
        st.caption(
            "For each (model, phase): bar height = (mean of the **selected** intervention "
            "replicas' round-success) − (mean of the **baseline** replicas' round-success), "
            "in percentage points. Baseline replicas are the unmodified resume-at-round runs "
            "(no knob overrides) from the same sources — they are the control and are always "
            "used as the reference regardless of the intervention filter. Bars above zero "
            "mean the intervention outperformed the baseline. Phase A (pre-first-swap rounds) "
            "is excluded — replicas inherit those rounds verbatim from the source JSONL clone."
        )
    intervention_counts: dict[str, int] = {}
    for resumes in resumes_by_source.values():
        for resume in resumes:
            tag = _extract_intervention_label(labels=resume.labels)
            intervention_counts[tag] = intervention_counts.get(tag, 0) + 1
    selected_interventions = render_horizontal_checkboxes(
        title="Intervention (replica tag)",
        options=[(t, t, intervention_counts[t]) for t in sorted(intervention_counts)],
        key_prefix=f"{key_prefix}_overview_intervention_filter",
    )
    if not selected_interventions:
        st.info("Select at least one intervention to populate the overview chart.")
        return
    intervention_filtered_resumes_by_source = _filter_resumes_by_intervention(
        resumes_by_source=resumes_by_source,
        selected_interventions=selected_interventions,
    )

    budget_counts: dict[str, int] = {}
    for resumes in intervention_filtered_resumes_by_source.values():
        for resume in resumes:
            budget = _extract_budget_label(labels=resume.labels)
            budget_counts[budget] = budget_counts.get(budget, 0) + 1
    selected_budgets = render_horizontal_checkboxes(
        title="Budget (replica tag)",
        options=[(b, b, budget_counts[b]) for b in sorted(budget_counts)],
        key_prefix=f"{key_prefix}_overview_budget_filter",
    )
    if not selected_budgets:
        st.info("Select at least one budget to populate the overview chart.")
        return
    budget_filtered_resumes_by_source = _filter_resumes_by_budget(
        resumes_by_source=intervention_filtered_resumes_by_source,
        selected_budgets=selected_budgets,
    )
    sources_data = _gather_sources_and_replicas(
        resumes_by_source=budget_filtered_resumes_by_source,
        evaluated_by_run_id=evaluated_by_run_id,
    )
    if not sources_data:
        st.info("No sources with evaluated replicas (after budget filter) to plot in the overview.")
        return
    model_counts: dict[str, int] = {}
    for _, source_run, replica_runs in sources_data:
        model_counts[source_run.primary_model] = model_counts.get(
            source_run.primary_model, 0
        ) + len(replica_runs)
    selected_models = render_horizontal_checkboxes(
        title="Model",
        options=[(m, m, model_counts[m]) for m in sorted(model_counts)],
        key_prefix=f"{key_prefix}_overview_model_filter",
    )
    filtered_sources_data = [
        triple for triple in sources_data if triple[1].primary_model in selected_models
    ]
    if not filtered_sources_data:
        st.info("Select at least one model to populate the overview chart.")
        return
    baseline_resumes_by_source = _filter_resumes_by_intervention(
        resumes_by_source=resumes_by_source,
        selected_interventions={_BASELINE_INTERVENTION_LABEL},
    )
    baseline_replicas_by_source: dict[str, list[MultiSwapRun]] = {}
    for source_id, resumes in baseline_resumes_by_source.items():
        replica_runs, _ = _build_replica_runs_for_source(
            resumes=resumes,
            evaluated_by_run_id=evaluated_by_run_id,
        )
        if replica_runs:
            baseline_replicas_by_source[source_id] = replica_runs
    baseline_total = sum(len(rs) for rs in baseline_replicas_by_source.values())

    source_count = len(filtered_sources_data)
    replica_count = sum(len(replicas) for _, _, replicas in filtered_sources_data)
    st.caption(
        f"Aggregating **{replica_count}** intervention replica(s) across **{source_count}** "
        f"source(s) vs **{baseline_total}** baseline replica(s) (the control: unmodified "
        f"resume-at-round runs with no knob overrides)."
    )
    buckets = _aggregate_by_model(
        sources_data=filtered_sources_data,
        baseline_replicas_by_source=baseline_replicas_by_source,
        mode=mode,
    )
    if not buckets:
        st.info("No post-Phase-A data to aggregate across the selected models.")
        return
    overview_fig = _build_model_delta_chart(buckets=buckets, mode=mode)
    st.plotly_chart(overview_fig, width="stretch", key=f"{key_prefix}_model_delta_chart_{mode}")
    _render_model_delta_table(buckets=buckets)
