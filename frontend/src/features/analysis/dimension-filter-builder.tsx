"use client";

/**
 * Narrowing a selection by what its dimension cells say.
 *
 * The values offered come from the field catalog, which read them off the selected
 * runs, so a filter can only ask for something that is actually there. A dimension
 * with more values than the catalog carries says so, and the text operators stay
 * available for the ones it did not list.
 */

import { Plus, X } from "lucide-react";
import type { AnalysisDimension, DimensionFilter } from "./use-analysis-data";

const OPERATORS: Array<{ value: DimensionFilter["operator"]; label: string }> = [
  { value: "in", label: "is one of" },
  { value: "not_in", label: "is not one of" },
  { value: "contains", label: "contains" },
  { value: "gte", label: "at least" },
  { value: "lte", label: "at most" },
  { value: "is_empty", label: "is empty" },
  { value: "is_not_empty", label: "is not empty" },
];

const VALUELESS_OPERATORS: Array<DimensionFilter["operator"]> = ["is_empty", "is_not_empty"];

/**
 * Whether a filter is finished enough to send.
 *
 * "Add filter" creates a row with no values chosen yet, and the server refuses a
 * comparing filter with nothing to compare against, correctly, since `in` with no
 * values matches nothing. An unfinished row is therefore left out of the query rather
 * than blanking every chart on the dashboard while someone is still picking.
 */
export function isCompleteFilter(filter: DimensionFilter): boolean {
  if (VALUELESS_OPERATORS.includes(filter.operator)) {
    return true;
  }
  return filter.values.length > 0;
}

function ValueControl({
  filter,
  dimension,
  onChange,
}: {
  filter: DimensionFilter;
  dimension: AnalysisDimension | undefined;
  onChange: (values: string[]) => void;
}) {
  if (VALUELESS_OPERATORS.includes(filter.operator)) {
    return null;
  }
  if (filter.operator === "in" || filter.operator === "not_in") {
    return (
      <select
        multiple
        value={filter.values}
        onChange={event =>
          onChange(Array.from(event.target.selectedOptions).map(option => option.value))
        }
        className="h-20 min-w-40 flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
      >
        {(dimension?.values ?? []).map(value => (
          <option key={value.value} value={value.value}>
            {value.value === "" ? "(empty)" : value.value} · {value.observation_count}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      value={filter.values[0] ?? ""}
      onChange={event => onChange([event.target.value])}
      className="min-w-32 flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
    />
  );
}

export function DimensionFilterBuilder({
  filters,
  dimensions,
  onChange,
}: {
  filters: DimensionFilter[];
  dimensions: AnalysisDimension[];
  onChange: (filters: DimensionFilter[]) => void;
}) {
  const replace = (index: number, filter: DimensionFilter) =>
    onChange(filters.map((existing, position) => (position === index ? filter : existing)));

  return (
    <div className="space-y-2">
      {filters.map((filter, index) => {
        const dimension = dimensions.find(entry => entry.key === filter.key);
        return (
          <div key={index} className="flex flex-wrap items-start gap-2">
            <select
              value={filter.key}
              onChange={event => replace(index, { ...filter, key: event.target.value })}
              className="min-w-44 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {dimensions.some(entry => entry.key === filter.key) ? null : (
                // The catalog may still be loading, or the grain may have changed out
                // from under a saved filter. Without this the browser shows the first
                // option while the state holds something else, and the two disagree
                // silently.
                <option value={filter.key}>{filter.key} (not in this selection)</option>
              )}
              {dimensions.map(entry => (
                <option key={entry.key} value={entry.key}>
                  {entry.key}
                </option>
              ))}
            </select>
            <select
              value={filter.operator}
              onChange={event =>
                replace(index, {
                  ...filter,
                  operator: event.target.value as DimensionFilter["operator"],
                  values: [],
                })
              }
              className="rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {OPERATORS.map(operator => (
                <option key={operator.value} value={operator.value}>
                  {operator.label}
                </option>
              ))}
            </select>
            <ValueControl
              filter={filter}
              dimension={dimension}
              onChange={values => replace(index, { ...filter, values })}
            />
            <button
              type="button"
              aria-label="Remove filter"
              onClick={() => onChange(filters.filter((_, position) => position !== index))}
              className="rounded-md border border-border p-1 text-muted-foreground hover:bg-muted"
            >
              <X className="h-3.5 w-3.5" />
            </button>
            {isCompleteFilter(filter) ? null : (
              <p className="w-full text-[11px] text-muted-foreground">
                Pick a value; until then this filter is left out of the query.
              </p>
            )}
            {dimension !== undefined && dimension.distinct_count > dimension.values.length ? (
              <p className="w-full text-[11px] text-muted-foreground">
                Showing {dimension.values.length} of {dimension.distinct_count} values for{" "}
                {dimension.key}. Use &quot;contains&quot; for one that is not listed.
              </p>
            ) : null}
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => {
          const first = dimensions[0];
          if (first === undefined) {
            return;
          }
          onChange([...filters, { key: first.key, operator: "in", values: [] }]);
        }}
        className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
      >
        <Plus className="h-3.5 w-3.5" />
        Add filter
      </button>
    </div>
  );
}
