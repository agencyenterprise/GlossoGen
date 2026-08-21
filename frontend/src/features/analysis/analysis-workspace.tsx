"use client";

/**
 * The analysis surface: a cohort, some filters, and the charts drawn over them.
 *
 * The dashboard owns the selection and the filters; charts inherit both. Changing the
 * cohort therefore re-points every chart at once, which is what makes a dashboard a
 * parameterised study rather than a set of unrelated pictures.
 *
 * Nothing is saved until Save is pressed, and a saved dashboard stores its queries
 * rather than its numbers, so reopening it re-runs them against whatever has been run
 * and evaluated since.
 */

import { useState } from "react";
import { BarChart3, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { ChartCard } from "./chart-card";
import { newChart, nextChartId } from "./chart-draft";
import { DimensionFilterBuilder } from "./dimension-filter-builder";
import { EMPTY_SELECTION, RunSelectionPanel } from "./run-selection-panel";
import { isNarrowedSelection } from "./selection-scope";
import type { DimensionFilter, RunSelection } from "./use-analysis-data";
import { useAnalysisFields } from "./use-analysis-data";
import { useQueryClient } from "@tanstack/react-query";
import {
  dashboardKey,
  useDashboard,
  useDashboardList,
  useDeleteDashboard,
  useSaveDashboard,
} from "./use-dashboards";
import type { ChartSpec, Dashboard } from "./use-dashboards";

interface OpenRequest {
  dashboardId: string;
  sequence: number;
}

interface WorkspaceState {
  dashboardId: string | null;
  name: string;
  description: string;
  selection: RunSelection;
  filters: DimensionFilter[];
  charts: ChartSpec[];
}

const BLANK: WorkspaceState = {
  dashboardId: null,
  name: "Untitled dashboard",
  description: "",
  selection: EMPTY_SELECTION,
  filters: [],
  charts: [],
};

/** The parts of a dashboard a save would send, as one comparable string. */
function contentOf(state: WorkspaceState): string {
  return JSON.stringify({
    name: state.name,
    description: state.description,
    selection: state.selection,
    filters: state.filters,
    charts: state.charts,
  });
}

function contentKey({ dashboard }: { dashboard: Dashboard }): string {
  return contentOf(stateOf(dashboard));
}

function stateOf(dashboard: Dashboard): WorkspaceState {
  return {
    dashboardId: dashboard.dashboard_id,
    name: dashboard.name,
    description: dashboard.description,
    selection: dashboard.selection,
    filters: dashboard.filters,
    charts: dashboard.charts,
  };
}

export function AnalysisWorkspace() {
  const [state, setState] = useState<WorkspaceState>(BLANK);
  // The request carries a sequence number so that opening the dashboard already on
  // screen still counts as a request. Keyed on the id alone, clicking it was a no-op,
  // which left no way to discard edits and get back to what is stored.
  const [openRequest, setOpenRequest] = useState<OpenRequest | null>(null);
  const [appliedSequence, setAppliedSequence] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedContent, setSavedContent] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const dashboards = useDashboardList();
  const save = useSaveDashboard();
  const remove = useDeleteDashboard();

  // The dashboard-level controls read the run grain: filters here narrow which runs
  // every chart sees, whatever grain each chart then counts at.
  const scoped = isNarrowedSelection(state.selection);
  const fields = useAnalysisFields({
    selection: state.selection,
    grain: "run",
    enabled: scoped,
  });

  const opening = useDashboard(openRequest?.dashboardId ?? null);
  if (
    opening.data !== undefined &&
    openRequest !== null &&
    appliedSequence !== openRequest.sequence
  ) {
    setAppliedSequence(openRequest.sequence);
    setState(stateOf(opening.data));
    setSavedContent(contentKey({ dashboard: opening.data }));
  }

  // A dashboard that has never been saved has no stored content to compare against,
  // so an empty one is the baseline. Without that, three charts built on a fresh
  // dashboard counted as unchanged and went without a prompt, which is the case the
  // prompt exists for.
  const dirty = contentOf(state) !== (savedContent ?? contentOf(BLANK));

  // A reopen that fails leaves the previous state on screen, since the apply waits
  // for data that never arrives. Saying so is the difference between that and a click
  // that did nothing.
  const problem = saveError ?? opening.error?.message ?? null;

  /** Open a dashboard, asking first when the one on screen has unsaved edits. */
  const open = (dashboardId: string) => {
    if (dirty && !window.confirm("Discard the unsaved changes on this dashboard?")) {
      return;
    }
    setSaveError(null);
    // Reset rather than invalidated. Invalidation marks the query stale and refetches
    // in the background while `data` keeps returning the copy already held, so the
    // apply below would fire on that copy and mark this request done before the fetch
    // resolved. Reset clears the data, so the apply waits for what is stored now,
    // which is the point: someone else in the group may have saved over it.
    void queryClient.resetQueries({ queryKey: dashboardKey(dashboardId) });
    setOpenRequest(current => ({ dashboardId, sequence: (current?.sequence ?? 0) + 1 }));
  };

  const update = (patch: Partial<WorkspaceState>) =>
    setState(current => ({ ...current, ...patch }));

  const addChart = () =>
    update({
      charts: [...state.charts, newChart(nextChartId(state.charts), fields.data?.measures ?? [])],
    });

  const onSave = () => {
    setSaveError(null);
    save.mutate(
      {
        dashboardId: state.dashboardId,
        content: {
          name: state.name,
          description: state.description,
          selection: state.selection,
          filters: state.filters,
          charts: state.charts,
        },
      },
      {
        onSuccess: dashboard => {
          setState(stateOf(dashboard));
          setSavedContent(contentKey({ dashboard }));
          setOpenRequest(current => ({
            dashboardId: dashboard.dashboard_id,
            sequence: (current?.sequence ?? 0) + 1,
          }));
          setAppliedSequence(current => current + 1);
        },
        onError: error => setSaveError(error.message),
      }
    );
  };

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <aside className="w-full shrink-0 lg:w-64">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Dashboards</h2>
          <button
            type="button"
            onClick={() => {
              if (dirty && !window.confirm("Discard the unsaved changes on this dashboard?")) {
                return;
              }
              setOpenRequest(null);
              setSavedContent(null);
              setState(BLANK);
            }}
            className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
          >
            New
          </button>
        </div>
        <ul className="space-y-1">
          {(dashboards.data ?? []).map(summary => (
            <li key={summary.dashboard_id}>
              <button
                type="button"
                onClick={() => open(summary.dashboard_id)}
                title={
                  summary.dashboard_id === state.dashboardId
                    ? "Reload this dashboard as it is stored"
                    : undefined
                }
                className={cn(
                  "w-full rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                  summary.dashboard_id === state.dashboardId
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted"
                )}
              >
                <span className="block font-medium">{summary.name}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {summary.chart_count === 1 ? "1 chart" : `${summary.chart_count} charts`} ·{" "}
                  {new Date(summary.updated_at).toISOString().slice(0, 10)}
                </span>
              </button>
            </li>
          ))}
          {dashboards.data?.length === 0 ? (
            <li className="rounded-md border border-dashed border-border px-2.5 py-3 text-xs text-muted-foreground">
              Nothing saved yet. Build a chart and press Save.
            </li>
          ) : null}
        </ul>
      </aside>

      <div className="min-w-0 flex-1 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-64 flex-1 space-y-2">
            <input
              type="text"
              value={state.name}
              onChange={event => update({ name: event.target.value })}
              className="w-full rounded-md border border-transparent bg-transparent text-2xl font-bold tracking-tight outline-none hover:border-border focus:border-primary"
            />
            <input
              type="text"
              value={state.description}
              placeholder="What this dashboard answers"
              onChange={event => update({ description: event.target.value })}
              className="w-full rounded-md border border-transparent bg-transparent text-sm text-muted-foreground outline-none hover:border-border focus:border-primary"
            />
          </div>
          <div className="flex items-center gap-2">
            {dirty ? <span className="text-xs text-muted-foreground">Unsaved changes</span> : null}
            <button
              type="button"
              onClick={onSave}
              disabled={save.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save
            </button>
            {state.dashboardId === null ? null : (
              <button
                type="button"
                onClick={() => {
                  const id = state.dashboardId;
                  if (id === null) {
                    return;
                  }
                  remove.mutate(id, {
                    onSuccess: () => {
                      setOpenRequest(null);
                      setSavedContent(null);
                      setState(BLANK);
                    },
                  });
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            )}
          </div>
        </div>

        {problem === null ? null : (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {problem}
          </p>
        )}

        <RunSelectionPanel
          selection={state.selection}
          onChange={selection => update({ selection })}
          runCount={fields.data?.run_count ?? null}
        />

        {scoped ? null : (
          <p className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground">
            Pick a scenario or a label to start. Charting every run at once reads every run&apos;s
            evaluation report, which is slow and rarely the question.
          </p>
        )}

        <section className="rounded-lg border border-border p-4">
          <h2 className="mb-2 text-sm font-semibold">Filters</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Applied to every chart below, on top of whatever each chart filters for itself.
          </p>
          <DimensionFilterBuilder
            filters={state.filters}
            dimensions={fields.data?.dimensions ?? []}
            onChange={filters => update({ filters })}
          />
        </section>

        {fields.data !== undefined && fields.data.runs_without_report.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            {fields.data.runs_without_report.length} of {fields.data.run_count} selected runs have
            no evaluation report. Their metric cells are empty rather than zero, so they lower no
            average.
          </p>
        ) : null}

        <div className="space-y-4">
          {state.charts.map(chart => (
            <ChartCard
              key={chart.chart_id}
              chart={chart}
              selection={state.selection}
              dashboardFilters={state.filters}
              onChange={next =>
                update({
                  charts: state.charts.map(existing =>
                    existing.chart_id === chart.chart_id ? next : existing
                  ),
                })
              }
              onRemove={() =>
                update({
                  charts: state.charts.filter(existing => existing.chart_id !== chart.chart_id),
                })
              }
            />
          ))}

          {state.charts.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border py-14">
              <BarChart3 className="h-6 w-6 text-muted-foreground" />
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                Pick a cohort above, then add a chart. Every chart is a query, so the numbers
                reproduce from <code className="text-xs">glossogen analyze</code>.
              </p>
            </div>
          ) : null}

          <button
            type="button"
            onClick={addChart}
            disabled={!scoped}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            Add chart
          </button>
        </div>
      </div>
    </div>
  );
}
