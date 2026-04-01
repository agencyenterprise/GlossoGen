"use client";

import { Fragment, useState } from "react";
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
import { useRouter } from "next/navigation";
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
  const router = useRouter();
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
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <tbody>
                {group.runs.map((run, idx) => {
                  const hasBadges =
                    run.fork_source ||
                    run.has_evaluation ||
                    (run.scenario_config && Object.keys(run.scenario_config).length > 0);
                  const bgClass =
                    run.status === "in_progress" ? "bg-green-50 dark:bg-green-950/20" : "";
                  const borderClass = idx > 0 ? "border-t border-border" : "";

                  return (
                    <Fragment key={run.run_id}>
                      <tr
                        className={`group cursor-pointer transition-colors hover:bg-accent/50 ${bgClass} ${borderClass}`}
                        onClick={() => {
                          router.push(`/runs/${run.run_id}`);
                        }}
                      >
                        <td className="whitespace-nowrap py-2 pl-4 font-medium">
                          <span className="inline-flex items-center gap-1.5">
                            {humanize(run.scenario_name)}
                            <button
                              aria-label="Scenario description"
                              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                              onClick={e => {
                                e.stopPropagation();
                                setModalRun(run);
                              }}
                            >
                              <HelpCircle className="h-3.5 w-3.5" />
                            </button>
                          </span>
                        </td>
                        <td
                          className="max-w-48 truncate px-3 py-2 text-muted-foreground"
                          title={run.models.join(", ")}
                        >
                          {run.models.join(", ")}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
                          {run.total_messages}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
                          {run.total_cost_usd > 0 ? formatCost(run.total_cost_usd) : "—"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
                          {run.duration_seconds > 0
                            ? formatDuration(run.duration_seconds)
                            : run.status === "in_progress"
                              ? formatDuration(elapsedSince(run.timestamp))
                              : "—"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right text-muted-foreground">
                          {formatTime(run.timestamp)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right">
                          <span
                            className={`text-xs font-medium ${
                              run.status === "in_progress"
                                ? "text-green-600 dark:text-green-400"
                                : run.status === "error"
                                  ? "text-destructive"
                                  : "text-muted-foreground"
                            }`}
                          >
                            {STATUS_LABELS[run.status] ?? run.status}
                          </span>
                        </td>
                        <td className="w-16 py-2 pr-4 text-right">
                          <span className="inline-flex items-center gap-1">
                            {run.status === "in_progress" ? (
                              <button
                                aria-label="Stop simulation"
                                className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                                onClick={e => {
                                  e.stopPropagation();
                                  stopMutation.mutate(run.run_id);
                                }}
                              >
                                <Sword className="h-3.5 w-3.5" />
                              </button>
                            ) : null}
                            <button
                              aria-label="Delete run"
                              className="rounded p-1 text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                              onClick={e => {
                                e.stopPropagation();
                                deleteMutation.mutate(run.run_id);
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </span>
                        </td>
                      </tr>
                      {hasBadges ? (
                        <tr
                          className={`cursor-pointer transition-colors hover:bg-accent/50 ${bgClass}`}
                          onClick={() => {
                            router.push(`/runs/${run.run_id}`);
                          }}
                        >
                          <td colSpan={8} className="pb-2 pl-4 pr-4">
                            <div className="flex flex-wrap items-center gap-1.5">
                              {run.fork_source ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                                  <GitFork className="h-2.5 w-2.5" />
                                  Fork
                                </span>
                              ) : null}
                              {run.has_evaluation ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                  <CheckCircle className="h-3 w-3" />
                                  Evaluated
                                </span>
                              ) : null}
                              {run.scenario_config && Object.keys(run.scenario_config).length > 0
                                ? Object.entries(run.scenario_config).map(([key, value]) => (
                                    <span
                                      key={key}
                                      className="inline-flex items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px]"
                                    >
                                      <span className="text-muted-foreground">{humanize(key)}</span>
                                      <span className="font-medium">
                                        {formatConfigValue(value)}
                                      </span>
                                    </span>
                                  ))
                                : null}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
