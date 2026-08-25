"use client";

/**
 * Which runs a dashboard is about.
 *
 * Scenario, labels, run id and status, the way the runs list offers them. The
 * selection is stored on the dashboard rather than on each chart, which is what lets one
 * control re-point a whole study at another cohort.
 *
 * The runs list also filters on knob values, and this panel does not, so a cohort
 * narrowed by a knob condition there cannot be charted here yet. The wire model carries
 * the field either way.
 */

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { useLabelDescriptions } from "@/shared/lib/use-label-descriptions";
import { Tooltip } from "@/shared/components/ui/tooltip";
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
  // This panel offers no knob control yet. Empty means the same as absent, so a
  // dashboard saved from here carries no knob condition either way.
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
  title,
  selected,
  onClick,
}: {
  label: string;
  title: string | undefined;
  selected: boolean;
  onClick: () => void;
}) {
  const button = (
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
  if (title === undefined) {
    return button;
  }
  return (
    <Tooltip label={title} wrap={true}>
      {button}
    </Tooltip>
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
  const labelDescriptions = useLabelDescriptions();

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
              title={undefined}
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
              title={labelDescriptions.get(label)}
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
