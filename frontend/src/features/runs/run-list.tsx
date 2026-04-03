"use client";

import { Fragment, useEffect, useRef, useState } from "react";
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
  formatConfigValueFull,
  formatCost,
  formatDuration,
  formatTime,
  humanize,
} from "./format";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { ConfigValueModal } from "./config-value-modal";

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
  starting: "Starting",
  error: "Error",
  killed: "Killed",
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
  const [configPreview, setConfigPreview] = useState<{ key: string; value: string } | null>(null);
  const [modelsPopover, setModelsPopover] = useState<{
    left: number;
    top: number;
    agentModels: RunSummary["agent_models"];
  } | null>(null);
  const closePopoverTimerRef = useRef<number | null>(null);
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => {
    return () => {
      if (closePopoverTimerRef.current !== null) {
        window.clearTimeout(closePopoverTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (modelsPopover === null) {
      return undefined;
    }
    const handleViewportChange = () => {
      setModelsPopover(null);
    };
    window.addEventListener("scroll", handleViewportChange, true);
    window.addEventListener("resize", handleViewportChange);
    return () => {
      window.removeEventListener("scroll", handleViewportChange, true);
      window.removeEventListener("resize", handleViewportChange);
    };
  }, [modelsPopover]);

  function clearModelsPopoverCloseTimer() {
    if (closePopoverTimerRef.current !== null) {
      window.clearTimeout(closePopoverTimerRef.current);
      closePopoverTimerRef.current = null;
    }
  }

  function queueModelsPopoverClose() {
    clearModelsPopoverCloseTimer();
    closePopoverTimerRef.current = window.setTimeout(() => {
      setModelsPopover(null);
      closePopoverTimerRef.current = null;
    }, 80);
  }

  function openModelsPopover(args: {
    targetElement: HTMLElement;
    agentModels: RunSummary["agent_models"];
  }) {
    clearModelsPopoverCloseTimer();
    const rect = args.targetElement.getBoundingClientRect();
    setModelsPopover({
      left: rect.left,
      top: rect.bottom + 4,
      agentModels: args.agentModels,
    });
  }

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
    refetchOnMount: "always",
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs");
      if (error) {
        throw new Error("Failed to fetch runs");
      }
      return data;
    },
    refetchInterval: query => {
      const hasActiveRun = query.state.data?.runs.some(
        r => r.status === "in_progress" || r.status === "starting"
      );
      if (hasActiveRun) {
        return 5000;
      }
      return 10000;
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

      {configPreview !== null ? (
        <ConfigValueModal
          configKey={configPreview.key}
          value={configPreview.value}
          onClose={() => setConfigPreview(null)}
          secondaryAction={null}
        />
      ) : null}

      {modelsPopover !== null ? (
        <div className="pointer-events-none fixed inset-0 z-50">
          <div
            className="pointer-events-auto absolute w-max max-w-sm rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg"
            style={{
              left: `${Math.max(8, modelsPopover.left)}px`,
              top: `${modelsPopover.top}px`,
            }}
            onMouseEnter={clearModelsPopoverCloseTimer}
            onMouseLeave={queueModelsPopoverClose}
            onClick={e => {
              e.stopPropagation();
            }}
          >
            {modelsPopover.agentModels.map(a => (
              <div key={a.agent_id} className="flex justify-between gap-4 py-0.5">
                <span className="text-muted-foreground">{a.role_name}</span>
                <span className="font-mono">
                  {a.provider}:{a.model}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {groups.map(group => (
        <div key={group.label}>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{group.label}</h2>
          <div className="rounded-lg border border-border">
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
                        <td className="max-w-48 px-3 py-2 text-muted-foreground">
                          {run.agent_models.length > 0 ? (
                            <span
                              className="inline-block max-w-full"
                              onMouseEnter={e => {
                                openModelsPopover({
                                  targetElement: e.currentTarget,
                                  agentModels: run.agent_models,
                                });
                              }}
                              onMouseLeave={queueModelsPopoverClose}
                            >
                              <span className="block truncate">{run.models.join(", ")}</span>
                            </span>
                          ) : (
                            <span className="block truncate" title={run.models.join(", ")}>
                              {run.models.join(", ")}
                            </span>
                          )}
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
                                    <button
                                      key={key}
                                      type="button"
                                      onClick={e => {
                                        e.stopPropagation();
                                        setConfigPreview({
                                          key,
                                          value: formatConfigValueFull(value),
                                        });
                                      }}
                                      className="inline-flex max-w-full items-center gap-0.5 rounded border border-border bg-muted/50 px-1.5 py-0 text-[11px] transition-colors hover:border-primary hover:bg-primary/5"
                                    >
                                      <span className="shrink-0 text-muted-foreground">
                                        {humanize(key)}
                                      </span>
                                      <span className="max-w-48 truncate font-medium">
                                        {formatConfigValue(value)}
                                      </span>
                                    </button>
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
