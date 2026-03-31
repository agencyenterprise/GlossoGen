"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  GitFork,
  HelpCircle,
  Inbox,
  Loader2,
  Sword,
  Trash2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import type { components } from "@/types/api.gen";
import {
  elapsedSince,
  formatConfigValue,
  formatCost,
  formatDuration,
  formatTime,
  humanize,
} from "./format";
import { ScenarioDescriptionModal } from "./scenario-description-modal";

type RunSummary = components["schemas"]["RunSummary"];

function formatDayHeader(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

type RunStatus = components["schemas"]["RunStatus"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  error: "Error",
};

function groupByDay(runs: RunSummary[]): Array<{ label: string; runs: RunSummary[] }> {
  const groups = new Map<string, { label: string; runs: RunSummary[] }>();
  for (const run of runs) {
    const key = dayKey(run.timestamp);
    const existing = groups.get(key);
    if (existing) {
      existing.runs.push(run);
    } else {
      groups.set(key, { label: formatDayHeader(run.timestamp), runs: [run] });
    }
  }
  return Array.from(groups.values());
}

export function RunList() {
  const [modalRun, setModalRun] = useState<RunSummary | null>(null);
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async (runId: string) => {
      const { error } = await api.DELETE("/api/runs/{run_id}", {
        params: { path: { run_id: runId } },
      });
      if (error) {
        throw new Error("Failed to delete run");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: async (runId: string) => {
      const { error } = await api.POST("/api/runs/{run_id}/stop", {
        params: { path: { run_id: runId } },
      });
      if (error) {
        throw new Error("Failed to stop simulation");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs");
      if (error) {
        throw new Error("Failed to fetch runs");
      }
      return data;
    },
    refetchInterval: query => {
      const hasInProgress = query.state.data?.runs.some(r => r.status === "in_progress");
      if (hasInProgress) {
        return 5000;
      }
      return false;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load runs</p>
      </div>
    );
  }

  const runs = data!.runs;

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-muted-foreground">
        <Inbox className="h-10 w-10" />
        <p>No simulation runs found</p>
      </div>
    );
  }

  const groups = groupByDay(runs);

  return (
    <div className="space-y-6">
      {modalRun !== null ? (
        <ScenarioDescriptionModal
          scenarioName={humanize(modalRun.scenario_name)}
          description={modalRun.scenario_description}
          onClose={() => setModalRun(null)}
        />
      ) : null}

      {groups.map(group => (
        <div key={group.label}>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{group.label}</h2>
          <div className="divide-y divide-border rounded-lg border border-border">
            {group.runs.map(run => (
              <Link
                key={run.run_id}
                href={`/runs/${run.run_id}`}
                className={`block px-4 py-2.5 text-sm transition-colors hover:bg-accent/50 ${run.status === "in_progress" ? "bg-green-50 dark:bg-green-950/20" : ""}`}
              >
                <div className="flex items-center gap-6">
                  <span className="flex w-40 items-center gap-1.5 font-medium">
                    {humanize(run.scenario_name)}
                    <button
                      aria-label="Scenario description"
                      className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      onClick={e => {
                        e.preventDefault();
                        setModalRun(run);
                      }}
                    >
                      <HelpCircle className="h-3.5 w-3.5" />
                    </button>
                    {run.fork_source ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                        <GitFork className="h-2.5 w-2.5" />
                        Fork
                      </span>
                    ) : null}
                  </span>
                  <span className="w-20 text-muted-foreground">{formatTime(run.timestamp)}</span>
                  <span
                    className="w-44 truncate text-muted-foreground"
                    title={run.models.join(", ")}
                  >
                    {run.models.join(", ")}
                  </span>
                  <span className="w-16 text-muted-foreground">{run.total_messages} msgs</span>
                  {run.total_cost_usd > 0 ? (
                    <span className="w-16 text-muted-foreground">
                      {formatCost(run.total_cost_usd)}
                    </span>
                  ) : null}
                  <span className="w-16 text-muted-foreground">
                    {run.duration_seconds > 0
                      ? formatDuration(run.duration_seconds)
                      : run.status === "in_progress"
                        ? formatDuration(elapsedSince(run.timestamp))
                        : null}
                  </span>
                  <span className="w-36 text-muted-foreground">
                    {STATUS_LABELS[run.status] ?? run.status}
                  </span>
                  <span className="ml-auto">
                    {run.has_evaluation ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                        <CheckCircle className="h-3 w-3" />
                        Evaluated
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                        No evaluation
                      </span>
                    )}
                  </span>
                  {run.status === "in_progress" ? (
                    <button
                      aria-label="Stop simulation"
                      className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                      onClick={e => {
                        e.preventDefault();
                        stopMutation.mutate(run.run_id);
                      }}
                    >
                      <Sword className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                  <button
                    aria-label="Delete run"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                    onClick={e => {
                      e.preventDefault();
                      deleteMutation.mutate(run.run_id);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {run.scenario_config && Object.keys(run.scenario_config).length > 0 ? (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {Object.entries(run.scenario_config).map(([key, value]) => (
                      <span
                        key={key}
                        className="inline-flex items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px]"
                      >
                        <span className="text-muted-foreground">{humanize(key)}</span>
                        <span className="font-medium">{formatConfigValue(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
