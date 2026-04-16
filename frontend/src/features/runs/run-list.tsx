"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  GitFork,
  HelpCircle,
  Inbox,
  Loader2,
  Package,
  StickyNote,
  Sword,
  Tag,
  Trash2,
  XCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { api, buildApiUrlWithToken } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
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
import { NoteViewModal } from "./note-view-modal";
import { LabelBadges } from "./eval-label-group";
import { labelColor } from "./label-picker-modal";

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
  const [noteModalRunId, setNoteModalRunId] = useState<string | null>(null);
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set());
  const [modelsPopover, setModelsPopover] = useState<{
    left: number;
    top: number;
    agentModels: RunSummary["agent_models"];
  } | null>(null);
  const closePopoverTimerRef = useRef<number | null>(null);
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: labelsData } = useQuery({
    queryKey: ["all-labels"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/labels");
      if (error) {
        throw new Error("Failed to fetch labels");
      }
      return data;
    },
  });

  function toggleLabel(label: string) {
    setSelectedLabels(prev => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  }

  function toggleScenario(scenario: string) {
    setSelectedScenarios(prev => {
      const next = new Set(prev);
      if (next.has(scenario)) {
        next.delete(scenario);
      } else {
        next.add(scenario);
      }
      return next;
    });
  }

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

  const allRuns = useMemo(() => data?.runs ?? [], [data]);
  const allLabels = labelsData?.labels ?? [];
  const allScenarios = useMemo(() => {
    const seen = new Set<string>();
    for (const run of allRuns) {
      seen.add(run.scenario_name);
    }
    return Array.from(seen).sort();
  }, [allRuns]);
  const runs = useMemo(() => {
    let filtered = allRuns;
    if (selectedScenarios.size > 0) {
      filtered = filtered.filter(run => selectedScenarios.has(run.scenario_name));
    }
    if (selectedLabels.size > 0) {
      filtered = filtered.filter(run =>
        [...selectedLabels].every(label => run.labels.includes(label))
      );
    }
    return filtered;
  }, [allRuns, selectedLabels, selectedScenarios]);

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

  if (allRuns.length === 0) {
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
      {allScenarios.length > 1 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Package className="h-3.5 w-3.5 text-muted-foreground" />
          {allScenarios.map(scenario => {
            const active = selectedScenarios.has(scenario);
            return (
              <button
                key={scenario}
                type="button"
                onClick={() => toggleScenario(scenario)}
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium transition-all",
                  active
                    ? "bg-primary/15 text-primary ring-1 ring-primary/30"
                    : "bg-muted/60 text-muted-foreground hover:bg-muted"
                )}
              >
                {humanize(scenario)}
              </button>
            );
          })}
          {selectedScenarios.size > 0 ? (
            <button
              type="button"
              onClick={() => setSelectedScenarios(new Set())}
              className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <XCircle className="h-3 w-3" />
              Clear
            </button>
          ) : null}
        </div>
      ) : null}

      {allLabels.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag className="h-3.5 w-3.5 text-muted-foreground" />
          {allLabels.map(label => {
            const active = selectedLabels.has(label);
            const color = labelColor(label);
            return (
              <button
                key={label}
                type="button"
                onClick={() => toggleLabel(label)}
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium transition-all",
                  active
                    ? `${color.bg} ${color.text} ring-1 ring-current`
                    : "bg-muted/60 text-muted-foreground hover:bg-muted"
                )}
              >
                {label}
              </button>
            );
          })}
          {selectedLabels.size > 0 ? (
            <button
              type="button"
              onClick={() => setSelectedLabels(new Set())}
              className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <XCircle className="h-3 w-3" />
              Clear
            </button>
          ) : null}
        </div>
      ) : null}

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

      {noteModalRunId !== null ? (
        <NoteViewModal runId={noteModalRunId} onClose={() => setNoteModalRunId(null)} />
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

      {runs.length === 0 && (selectedLabels.size > 0 || selectedScenarios.size > 0) ? (
        <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
          <Inbox className="h-8 w-8" />
          <p className="text-sm">No runs match the selected filters</p>
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
                    run.labels.length > 0 ||
                    run.has_note ||
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
                            <span className="group/help relative">
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
                              <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/help:block">
                                Scenario description
                              </span>
                            </span>
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
                              <span className="group/stop relative">
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
                                <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/stop:block">
                                  Stop simulation
                                </span>
                              </span>
                            ) : null}
                            <span className="group/export relative">
                              <button
                                aria-label="Export bundle"
                                className="rounded p-1 text-muted-foreground opacity-0 transition-all hover:bg-muted hover:text-foreground group-hover:opacity-100"
                                onClick={e => {
                                  e.stopPropagation();
                                  const url = buildApiUrlWithToken({
                                    path: `/api/runs/${run.run_id}/export/bundle`,
                                    searchParams: new URLSearchParams(),
                                  });
                                  window.open(url, "_blank");
                                }}
                              >
                                <Package className="h-3.5 w-3.5" />
                              </button>
                              <span className="pointer-events-none absolute right-0 top-full z-50 mt-1 hidden whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/export:block">
                                Export bundle
                              </span>
                            </span>
                            <span className="group/delete relative">
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
                              <span className="pointer-events-none absolute right-0 top-full z-50 mt-1 hidden whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/delete:block">
                                Delete run
                              </span>
                            </span>
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
                              <LabelBadges labels={run.labels} size="sm" />
                              {run.has_note ? (
                                <button
                                  type="button"
                                  className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-1.5 py-0.5 text-[10px] font-medium text-yellow-700 transition-colors hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:hover:bg-yellow-900/50"
                                  onClick={e => {
                                    e.stopPropagation();
                                    setNoteModalRunId(run.run_id);
                                  }}
                                >
                                  <StickyNote className="h-2.5 w-2.5" />
                                  Note
                                </button>
                              ) : null}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-1.5">
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
