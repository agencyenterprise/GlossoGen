"use client";

/**
 * The controls behind one chart: what it counts, how it groups, and how it draws.
 *
 * Every field offered comes from the field catalog for the current selection and
 * grain, so the builder cannot compose a query the data cannot answer. Measures carry
 * how many rows have a number for them, which is what separates a metric that ran on
 * this cohort from one that only exists elsewhere.
 */

import { Plus, X } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { AGGREGATES, CHART_KINDS, clampEncoding, requiredGroupKeys } from "./chart-draft";
import type {
  AnalysisFieldCatalog,
  AnalysisGrain,
  AnalysisQuerySpec,
  MeasureSpec,
} from "./use-analysis-data";
import type { ChartSpec } from "./use-dashboards";

const GRAINS: AnalysisGrain[] = ["run", "round", "agent", "keyed"];

const NO_KEY = "";

function measureValue(measure: MeasureSpec): string {
  return `${measure.source}:${measure.key}`;
}

export function ChartBuilderPanel({
  chart,
  catalog,
  onChange,
  onGrainChange,
}: {
  chart: ChartSpec;
  catalog: AnalysisFieldCatalog | undefined;
  onChange: (chart: ChartSpec) => void;
  onGrainChange: (grain: AnalysisGrain) => void;
}) {
  const dimensions = catalog?.dimensions ?? [];
  const measures = catalog?.measures ?? [];
  const query = chart.query;

  const setQuery = (patch: Partial<AnalysisQuerySpec>) =>
    onChange({ ...chart, query: { ...query, ...patch } });

  const setGroupKey = (position: number, key: string) => {
    const next = [...query.group_by];
    if (key === NO_KEY) {
      next.splice(position);
    } else {
      next[position] = key;
    }
    setQuery({ group_by: next.filter(entry => entry !== undefined && entry !== NO_KEY) });
  };

  const setMeasure = (index: number, patch: Partial<MeasureSpec>) =>
    setQuery({
      measures: query.measures.map((measure, position) =>
        position === index ? { ...measure, ...patch } : measure
      ),
    });

  const needsTwoKeys = requiredGroupKeys(chart.kind) === 2;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Title</span>
          <input
            type="text"
            value={chart.title}
            onChange={event => onChange({ ...chart, title: event.target.value })}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          />
        </label>
        <div className="text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Chart</span>
          <div className="flex flex-wrap gap-1">
            {CHART_KINDS.map(kind => (
              <button
                key={kind}
                type="button"
                onClick={() => onChange({ ...chart, kind })}
                className={cn(
                  "rounded-md border px-2.5 py-1 capitalize transition-colors",
                  chart.kind === kind
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "border-border text-muted-foreground hover:bg-muted"
                )}
              >
                {kind}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">One row is a</span>
          <select
            value={query.grain}
            onChange={event => onGrainChange(event.target.value as AnalysisGrain)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          >
            {GRAINS.map(grain => (
              <option key={grain} value={grain}>
                {grain === "keyed" ? "metric key (category, question, message)" : grain}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Group by (x axis)</span>
          <select
            value={query.group_by[0] ?? NO_KEY}
            onChange={event => setGroupKey(0, event.target.value)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          >
            <option value={NO_KEY}>Everything in one group</option>
            {dimensions.map(dimension => (
              <option key={dimension.key} value={dimension.key}>
                {dimension.key} ({dimension.distinct_count})
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">
            Then by (series){needsTwoKeys ? " — required" : ""}
          </span>
          <select
            value={query.group_by[1] ?? NO_KEY}
            disabled={query.group_by.length === 0}
            onChange={event => setGroupKey(1, event.target.value)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary disabled:opacity-50"
          >
            <option value={NO_KEY}>No series</option>
            {dimensions.map(dimension => (
              <option key={dimension.key} value={dimension.key}>
                {dimension.key} ({dimension.distinct_count})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Measures</p>
        {query.measures.map((measure, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2">
            <select
              value={measureValue(measure)}
              onChange={event => {
                const [source, ...rest] = event.target.value.split(":");
                setMeasure(index, {
                  source: source === "run_column" ? "run_column" : "metric",
                  key: rest.join(":"),
                });
              }}
              className="min-w-56 flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {measures.some(
                entry => `${entry.source}:${entry.key}` === measureValue(measure)
              ) ? null : (
                // A saved chart can name a measure this grain has no rows for, and
                // the catalog is empty while it loads. Showing the stored value
                // keeps the control and the state from disagreeing.
                <option value={measureValue(measure)}>{measure.key} (not at this grain)</option>
              )}
              {measures.map(entry => (
                <option key={`${entry.source}:${entry.key}`} value={`${entry.source}:${entry.key}`}>
                  {entry.key} · {entry.rows_with_value} rows
                  {entry.score_unit === "" ? "" : ` · ${entry.score_unit}`}
                </option>
              ))}
            </select>
            <select
              value={measure.aggregate}
              onChange={event =>
                setMeasure(index, { aggregate: event.target.value as MeasureSpec["aggregate"] })
              }
              className="rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {AGGREGATES.map(aggregate => (
                <option key={aggregate} value={aggregate}>
                  {aggregate}
                </option>
              ))}
            </select>
            {query.measures.length > 1 ? (
              <button
                type="button"
                aria-label="Remove measure"
                onClick={() => {
                  const measures = query.measures.filter((_, position) => position !== index);
                  onChange({
                    ...chart,
                    query: {
                      ...query,
                      measures,
                      sort_measure_index: Math.min(
                        query.sort_measure_index,
                        Math.max(0, measures.length - 1)
                      ),
                    },
                    encoding: clampEncoding(chart.encoding, measures.length),
                  });
                }}
                className="rounded-md border border-border p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        ))}
        <button
          type="button"
          onClick={() => {
            const first = measures[0];
            if (first === undefined) {
              return;
            }
            setQuery({
              measures: [
                ...query.measures,
                {
                  source: first.source === "run_column" ? "run_column" : "metric",
                  key: first.key,
                  aggregate: "mean",
                },
              ],
            });
          }}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
        >
          <Plus className="h-3.5 w-3.5" />
          Add measure
        </button>
        {query.group_by.length > 1 && query.measures.length > 1 ? (
          <p className="text-[11px] text-muted-foreground">
            With a series key only the first measure is drawn; the others stay in the table.
          </p>
        ) : null}
      </div>

      {(chart.kind === "bar" || chart.kind === "line") && query.measures.length > 1 ? (
        <label className="block max-w-xs text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Error bars from</span>
          <select
            value={chart.encoding.error_measure_index ?? ""}
            onChange={event =>
              onChange({
                ...chart,
                encoding: {
                  ...chart.encoding,
                  error_measure_index:
                    event.target.value === "" ? null : Number(event.target.value),
                },
              })
            }
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          >
            <option value="">None</option>
            {query.measures.map((measure, index) =>
              // Not the measure being drawn: error bars are drawn on it, and taking it
              // out of the series would leave the chart with nothing in it.
              index === chart.encoding.measure_index ? null : (
                <option key={index} value={index}>
                  {measure.key} ({measure.aggregate})
                </option>
              )
            )}
          </select>
          <span className="mt-1 block text-[11px] text-muted-foreground">
            Add the same metric a second time as sem or stddev, then pick it here. It is drawn on
            the measure above rather than as a series of its own.
          </span>
        </label>
      ) : null}

      {chart.kind === "scatter" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-muted-foreground">X axis measure</span>
            <select
              value={chart.encoding.measure_index}
              onChange={event =>
                onChange({
                  ...chart,
                  encoding: { ...chart.encoding, measure_index: Number(event.target.value) },
                })
              }
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
            >
              {query.measures.map((measure, index) => (
                <option key={index} value={index}>
                  {measure.key} ({measure.aggregate})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-muted-foreground">Y axis measure</span>
            <select
              value={chart.encoding.y_measure_index}
              onChange={event =>
                onChange({
                  ...chart,
                  encoding: { ...chart.encoding, y_measure_index: Number(event.target.value) },
                })
              }
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
            >
              {query.measures.map((measure, index) => (
                <option key={index} value={index}>
                  {measure.key} ({measure.aggregate})
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
    </div>
  );
}
