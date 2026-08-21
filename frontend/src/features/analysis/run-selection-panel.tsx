"use client";

/**
 * Which runs a dashboard is about.
 *
 * The same filters the runs list uses, so a cohort someone can see in the list is one
 * they can chart. The selection is stored on the dashboard rather than on each chart,
 * which is what lets one control re-point a whole study at another cohort.
 */

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import type { RunSelection } from "./use-analysis-data";

type FilterRunSelection = components["schemas"]["FilterRunSelection"];
type RunStatus = components["schemas"]["RunStatus"];

const STATUSES: RunStatus[] = ["scenario_complete", "in_progress", "error", "killed"];

export const EMPTY_SELECTION: FilterRunSelection = {
  kind: "filters",
  scenario: [],
  labels: [],
  run_id_contains: null,
  status: null,
  contains_agent_id: null,
  // This panel offers no knob control yet. The field is required on the wire,
  // and empty means the same as absent: no knob condition narrows the cohort.
  knob: [],
};

function useScenarioNames() {
  return useQuery({
    queryKey: ["analysis-scenario-names"],
    queryFn: async () => {
      const { data } = await api.GET("/api/g/{group_slug}/scenarios");
      return (data?.scenarios ?? []).map(scenario => scenario.scenario_name);
    },
  });
}

function useLabels() {
  return useQuery({
    queryKey: ["analysis-labels"],
    queryFn: async () => {
      const { data } = await api.GET("/api/g/{group_slug}/labels");
      return data?.labels ?? [];
    },
  });
}

function toggled(values: string[], value: string): string[] {
  if (values.includes(value)) {
    return values.filter(existing => existing !== value);
  }
  return [...values, value];
}

function Chip({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors",
        selected
          ? "border-primary bg-primary/10 font-medium text-primary"
          : "border-border text-muted-foreground hover:bg-muted"
      )}
    >
      {selected ? <Check className="h-3 w-3" /> : null}
      {label}
    </button>
  );
}

export function RunSelectionPanel({
  selection,
  onChange,
  runCount,
}: {
  selection: RunSelection;
  onChange: (selection: RunSelection) => void;
  runCount: number | null;
}) {
  const scenarios = useScenarioNames();
  const labels = useLabels();

  if (selection.kind === "explicit") {
    return (
      <section className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Runs</h2>
        <p className="mt-2 text-xs text-muted-foreground">
          {selection.run_ids.length} runs chosen one by one.
        </p>
        <button
          type="button"
          onClick={() => onChange(EMPTY_SELECTION)}
          className="mt-3 rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
        >
          Switch to filters
        </button>
      </section>
    );
  }

  const update = (patch: Partial<FilterRunSelection>) => onChange({ ...selection, ...patch });

  return (
    <section className="space-y-4 rounded-lg border border-border p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Runs</h2>
        <span className="text-xs text-muted-foreground">
          {runCount === null ? "…" : `${runCount} selected`}
        </span>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Scenario</p>
        <div className="flex flex-wrap gap-1.5">
          {(scenarios.data ?? []).map(name => (
            <Chip
              key={name}
              label={name}
              selected={selection.scenario.includes(name)}
              onClick={() => update({ scenario: toggled(selection.scenario, name) })}
            />
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
          Labels (a run must carry every one)
        </p>
        <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
          {(labels.data ?? []).map(label => (
            <Chip
              key={label}
              label={label}
              selected={selection.labels.includes(label)}
              onClick={() => update({ labels: toggled(selection.labels, label) })}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Run id contains</span>
          <input
            type="text"
            value={selection.run_id_contains ?? ""}
            onChange={event =>
              update({ run_id_contains: event.target.value === "" ? null : event.target.value })
            }
            placeholder="e.g. veyru/17776"
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          />
        </label>
        <label className="block text-xs">
          <span className="mb-1 block font-medium text-muted-foreground">Status</span>
          <select
            value={selection.status ?? ""}
            onChange={event =>
              update({
                status: event.target.value === "" ? null : (event.target.value as RunStatus),
              })
            }
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
          >
            <option value="">Any status</option>
            {STATUSES.map(status => (
              <option key={status} value={status}>
                {status.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
