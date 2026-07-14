"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, Loader2, Package, Search, Tag, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import { useActiveGroupSlug } from "@/features/auth/group-context";
import { formatDayHeader, humanize } from "./format";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { ConfigValueModal } from "./config-value-modal";
import { NoteViewModal } from "./note-view-modal";
import { labelColor } from "./label-picker-modal";
import { RunRow } from "./run-row";

type RunSummary = components["schemas"]["RunSummary"];

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

const PAGE_SIZE = 50;

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
  const [idSearch, setIdSearch] = useState("");
  const [idSearchDebounced, setIdSearchDebounced] = useState("");
  const [modelsPopover, setModelsPopover] = useState<{
    left: number;
    top: number;
    agentModels: RunSummary["agent_models"];
  } | null>(null);
  const closePopoverTimerRef = useRef<number | null>(null);
  const router = useRouter();
  const groupSlug = useActiveGroupSlug();
  const queryClient = useQueryClient();

  const navigateToRun = useCallback(
    (runId: string, event: MouseEvent) => {
      const url = `/g/${groupSlug}/runs/${runId}`;
      if (event.metaKey || event.ctrlKey) {
        window.open(url, "_blank");
      } else {
        router.push(url);
      }
    },
    [groupSlug, router]
  );

  const { data: labelsData } = useQuery({
    queryKey: ["all-labels"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/labels");
      if (error) {
        throw new Error("Failed to fetch labels");
      }
      return data;
    },
  });

  const { data: scenariosData } = useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/scenarios");
      if (error) {
        throw new Error("Failed to fetch scenarios");
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
    const handle = window.setTimeout(() => setIdSearchDebounced(idSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [idSearch]);

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

  const clearModelsPopoverCloseTimer = useCallback(() => {
    if (closePopoverTimerRef.current !== null) {
      window.clearTimeout(closePopoverTimerRef.current);
      closePopoverTimerRef.current = null;
    }
  }, []);

  const queueModelsPopoverClose = useCallback(() => {
    clearModelsPopoverCloseTimer();
    closePopoverTimerRef.current = window.setTimeout(() => {
      setModelsPopover(null);
      closePopoverTimerRef.current = null;
    }, 80);
  }, [clearModelsPopoverCloseTimer]);

  const openModelsPopover = useCallback(
    (targetElement: HTMLElement, agentModels: RunSummary["agent_models"]) => {
      clearModelsPopoverCloseTimer();
      const rect = targetElement.getBoundingClientRect();
      setModelsPopover({
        left: rect.left,
        top: rect.bottom + 4,
        agentModels,
      });
    },
    [clearModelsPopoverCloseTimer]
  );

  const deleteMutation = useMutation({
    mutationFn: async (runId: string) => {
      const { error } = await api.DELETE("/api/g/{group_slug}/runs/{scenario}/{run_dir_name}", {
        params: { path: splitRunId(runId) },
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
      const { error } = await api.POST("/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/stop", {
        params: { path: splitRunId(runId) },
      });
      if (error) {
        throw new Error("Failed to stop simulation");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const scenarioFilter = useMemo(() => [...selectedScenarios].sort(), [selectedScenarios]);
  const labelFilter = useMemo(() => [...selectedLabels].sort(), [selectedLabels]);

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: [
        "runs",
        { scenarios: scenarioFilter, labels: labelFilter, runId: idSearchDebounced },
      ],
      refetchOnMount: "always",
      initialPageParam: 0,
      queryFn: async ({ pageParam }) => {
        const { data, error } = await api.GET("/api/g/{group_slug}/runs", {
          params: {
            query: {
              offset: pageParam,
              limit: PAGE_SIZE,
              scenario: scenarioFilter.length > 0 ? scenarioFilter : undefined,
              labels: labelFilter.length > 0 ? labelFilter : undefined,
              run_id_contains: idSearchDebounced.length > 0 ? idSearchDebounced : undefined,
            },
          },
        });
        if (error) {
          throw new Error("Failed to fetch runs");
        }
        return data;
      },
      getNextPageParam: (lastPage, allPages) => {
        const loaded = allPages.reduce((sum, page) => sum + page.runs.length, 0);
        if (loaded < lastPage.total) {
          return loaded;
        }
        return undefined;
      },
      refetchInterval: query => {
        const hasActiveRun = query.state.data?.pages.some(page =>
          page.runs.some(r => r.status === "in_progress" || r.status === "starting")
        );
        if (hasActiveRun) {
          return 5000;
        }
        return 10000;
      },
    });

  const runs = useMemo(() => {
    // Offset pagination can surface a boundary run on two adjacent pages when
    // new runs are created between fetches (active polling + in-progress runs
    // shift every offset). Dedupe by run_id, keeping the newest occurrence.
    const byId = new Map<string, RunSummary>();
    for (const page of data?.pages ?? []) {
      for (const run of page.runs) {
        if (!byId.has(run.run_id)) {
          byId.set(run.run_id, run);
        }
      }
    }
    return [...byId.values()];
  }, [data]);
  const groups = useMemo(() => groupByDay(runs), [runs]);
  const totalRuns = data?.pages[0]?.total ?? 0;
  const allLabels = useMemo(() => labelsData?.labels ?? [], [labelsData]);
  const regularFilterLabels = useMemo(
    () => allLabels.filter(label => !label.startsWith("eval:") && !label.startsWith("src=")),
    [allLabels]
  );
  const allScenarios = useMemo(
    () => (scenariosData?.scenarios ?? []).map(s => s.scenario_name).sort(),
    [scenariosData]
  );
  const hasActiveFilters =
    selectedLabels.size > 0 || selectedScenarios.size > 0 || idSearchDebounced.length > 0;

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

  if (runs.length === 0 && !hasActiveFilters) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-muted-foreground">
        <Inbox className="h-10 w-10" />
        <p>No simulation runs found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="relative max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={idSearch}
          onChange={e => setIdSearch(e.target.value)}
          placeholder="Search by run id…"
          className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-7 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
        />
        {idSearch.length > 0 ? (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => setIdSearch("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
          >
            <XCircle className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

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

      {regularFilterLabels.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag className="h-3.5 w-3.5 text-muted-foreground" />
          {regularFilterLabels.map(label => {
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
          {selectedLabels.size > 0 && regularFilterLabels.some(l => selectedLabels.has(l)) ? (
            <button
              type="button"
              onClick={() => {
                setSelectedLabels(prev => {
                  const next = new Set(prev);
                  for (const label of regularFilterLabels) {
                    next.delete(label);
                  }
                  return next;
                });
              }}
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

      {runs.length === 0 && hasActiveFilters ? (
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
                {group.runs.map((run, idx) => (
                  <RunRow
                    key={run.run_id}
                    run={run}
                    showTopBorder={idx > 0}
                    onNavigate={navigateToRun}
                    onShowDescription={setModalRun}
                    onModelsEnter={openModelsPopover}
                    onModelsLeave={queueModelsPopoverClose}
                    onStop={stopMutation.mutate}
                    onDelete={deleteMutation.mutate}
                    onShowNote={setNoteModalRunId}
                    onConfigPreview={setConfigPreview}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {runs.length > 0 ? (
        <div className="flex flex-col items-center gap-2 pt-2">
          {hasNextPage ? (
            <button
              type="button"
              onClick={() => void fetchNextPage()}
              disabled={isFetchingNextPage}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-60"
            >
              {isFetchingNextPage ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Load more
            </button>
          ) : null}
          <p className="text-[11px] text-muted-foreground">
            Showing {runs.length} of {totalRuns}
          </p>
        </div>
      ) : null}
    </div>
  );
}
