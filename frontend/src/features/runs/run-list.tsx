"use client";

import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { Inbox, Loader2, Package, Search, Tag, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { splitRunId } from "@/shared/lib/run-id";
import { useLabelDescriptions } from "@/shared/lib/use-label-descriptions";
import { Tooltip } from "@/shared/components/ui/tooltip";
import type { components } from "@/types/api.gen";
import { useActiveGroupSlug } from "@/features/auth/group-context";
import { formatDayHeader, humanize } from "./format";
import { ConfigValueModal } from "./config-value-modal";
import { NoteViewModal } from "./note-view-modal";
import { KnobFilterBar } from "./knob-filter-bar";
import { parseKnobFilter } from "./knob-filter-encoding";
import { labelColor } from "./label-picker-modal";
import { RunRow, RunTableColumns } from "./run-row";
import { useRunExportSelection } from "./run-export-selection-context";

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
  const {
    picking,
    stopPicking,
    openExport,
    selectedRunIds,
    toggleRunSelected,
    replaceSelection,
    clearSelection,
    publishFilters,
    publishMatchingRunCount,
  } = useRunExportSelection();
  const [configPreview, setConfigPreview] = useState<{ key: string; value: string } | null>(null);
  const [noteModalRunId, setNoteModalRunId] = useState<string | null>(null);
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set());
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set());
  const [knobFilters, setKnobFilters] = useState<string[]>([]);
  // Whether leaving a single-scenario selection actually discarded conditions,
  // so the note below reports a drop only when one happened.
  const [droppedKnobFilters, setDroppedKnobFilters] = useState(false);
  const [idSearch, setIdSearch] = useState("");
  const [idSearchDebounced, setIdSearchDebounced] = useState("");
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

  const labelDescriptions = useLabelDescriptions();

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
    // Whether the click lands on a single-scenario selection, which is the only
    // one the knob bar can serve. Read from this render for the message only;
    // the selection itself still updates functionally.
    const leavesOneSelected = selectedScenarios.has(scenario)
      ? selectedScenarios.size === 2
      : selectedScenarios.size === 0;
    // A knob condition is written against one scenario's knobs schema, so it
    // means nothing once the selection names a different one.
    setKnobFilters([]);
    setDroppedKnobFilters(!leavesOneSelected && knobFilters.length > 0);
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
  // Knobs belong to one scenario's schema, so a condition built against one
  // scenario means nothing against another. Offer the builder only when a single
  // scenario is picked, and drop the conditions when that changes.
  const knobFilterScenario = scenarioFilter.length === 1 ? (scenarioFilter[0] ?? null) : null;
  const labelFilter = useMemo(() => [...selectedLabels].sort(), [selectedLabels]);

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: [
        "runs",
        {
          scenarios: scenarioFilter,
          labels: labelFilter,
          runId: idSearchDebounced,
          knobs: knobFilters,
        },
      ],
      refetchOnMount: "always",
      initialPageParam: null as string | null,
      queryFn: async ({ pageParam }) => {
        const { data, error } = await api.GET("/api/g/{group_slug}/runs", {
          params: {
            query: {
              cursor: pageParam ?? undefined,
              limit: PAGE_SIZE,
              scenario: scenarioFilter.length > 0 ? scenarioFilter : undefined,
              labels: labelFilter.length > 0 ? labelFilter : undefined,
              run_id_contains: idSearchDebounced.length > 0 ? idSearchDebounced : undefined,
              knob: knobFilters.length > 0 ? knobFilters : undefined,
            },
          },
        });
        if (error) {
          throw new Error("Failed to fetch runs");
        }
        return data;
      },
      // Keyset paging: the server returns the cursor for the next page directly,
      // so pages stay stable even as new runs appear at the top of the list.
      getNextPageParam: lastPage => lastPage.next_cursor ?? undefined,
      refetchInterval: query => {
        const hasActiveRun = query.state.data?.pages.some(page =>
          page.runs.some(r => r.status === "in_progress" || r.status === "starting")
        );
        // Only poll while something is live. A fully-settled historical list
        // does not change, so idle polling (which refetches every loaded page)
        // is pure waste.
        if (hasActiveRun) {
          return 5000;
        }
        return false;
      },
    });

  const runs = useMemo(() => {
    // Keyset pages are stable, but a boundary run can still appear twice if it
    // is created between the fetches of two adjacent pages. Dedupe by run_id as
    // a cheap safety net, keeping the first (newest-page) occurrence.
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
  // The picking bar renders above the virtualized list, so whether it is present
  // changes where that list starts on the page.
  const totalRuns = data?.pages[0]?.total ?? 0;

  // The knobs the current conditions ask about, so each row can show what it
  // recorded for them. Deduplicated: two conditions on one knob is one column.
  const filteredKnobNames = useMemo(() => {
    const names: string[] = [];
    for (const raw of knobFilters) {
      const parsed = parseKnobFilter(raw);
      if (parsed !== null && !names.includes(parsed.knob)) {
        names.push(parsed.knob);
      }
    }
    return names;
  }, [knobFilters]);

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
    selectedLabels.size > 0 ||
    selectedScenarios.size > 0 ||
    idSearchDebounced.length > 0 ||
    knobFilters.length > 0;

  // What the selection would show with the innermost narrowing removed, so the
  // ratio says what that narrowing cost. Knob conditions are the innermost, so
  // they come off first; with none set, the comparison is against the group.
  const baselineIgnoresKnobsOnly = knobFilters.length > 0;
  const baselineScenarios = baselineIgnoresKnobsOnly ? scenarioFilter : [];
  const baselineLabels = baselineIgnoresKnobsOnly ? labelFilter : [];
  const baselineRunId = baselineIgnoresKnobsOnly ? idSearchDebounced : "";
  const baselineLabel = baselineIgnoresKnobsOnly
    ? "matching the other filters, before the knob conditions"
    : "in this group";
  const { data: baselineTotal } = useQuery({
    queryKey: ["runs-baseline-total", baselineScenarios, baselineLabels, baselineRunId],
    enabled: hasActiveFilters,
    staleTime: 30_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/runs", {
        params: {
          query: {
            limit: 1,
            scenario: baselineScenarios.length > 0 ? baselineScenarios : undefined,
            labels: baselineLabels.length > 0 ? baselineLabels : undefined,
            run_id_contains: baselineRunId.length > 0 ? baselineRunId : undefined,
          },
        },
      });
      if (error) {
        throw new Error("Failed to count runs");
      }
      return data.total;
    },
  });

  // Window-scroll virtualization of the day-group cards. The page itself
  // scrolls (no inner scroll container), so off-screen day cards unmount while
  // the whole run table/card markup is otherwise untouched. `scrollMargin` is
  // the distance from the document top to the list, remeasured when the filter
  // area above it changes height or the window resizes.
  const listRef = useRef<HTMLDivElement | null>(null);
  const [listScrollMargin, setListScrollMargin] = useState(0);
  useLayoutEffect(() => {
    const measure = () => {
      if (listRef.current !== null) {
        setListScrollMargin(listRef.current.getBoundingClientRect().top + window.scrollY);
      }
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [
    allScenarios.length,
    regularFilterLabels.length,
    selectedScenarios.size,
    selectedLabels.size,
    picking,
  ]);

  const groupVirtualizer = useWindowVirtualizer({
    count: groups.length,
    estimateSize: () => 320,
    overscan: 3,
    scrollMargin: listScrollMargin,
  });

  // The export modal offers "everything matching the current filters", which is
  // the only honest way to express it: the list is paginated and virtualized, so
  // runs past the loaded pages have no id on the client to check.
  useEffect(() => {
    publishFilters({
      scenario: scenarioFilter,
      labels: labelFilter,
      run_id_contains: idSearchDebounced.length > 0 ? idSearchDebounced : null,
      status: null,
      contains_agent_id: null,
      knob: knobFilters,
    });
  }, [scenarioFilter, labelFilter, idSearchDebounced, knobFilters, publishFilters]);

  useEffect(() => {
    publishMatchingRunCount(totalRuns);
  }, [totalRuns, publishMatchingRunCount]);

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
              onClick={() => {
                setKnobFilters([]);
                setDroppedKnobFilters(false);
                setSelectedScenarios(new Set());
              }}
              className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <XCircle className="h-3 w-3" />
              Clear
            </button>
          ) : null}
        </div>
      ) : null}

      {knobFilterScenario !== null ? (
        <KnobFilterBar
          scenarioName={knobFilterScenario}
          filters={knobFilters}
          onChange={setKnobFilters}
        />
      ) : null}

      {knobFilterScenario === null && selectedScenarios.size > 1 ? (
        <p className="text-[11px] text-muted-foreground">
          Knob filtering needs a single scenario: knobs are declared per scenario, so a condition
          means nothing across two.
          {droppedKnobFilters ? " The conditions you had set were dropped." : null}
        </p>
      ) : null}

      {regularFilterLabels.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag className="h-3.5 w-3.5 text-muted-foreground" />
          {regularFilterLabels.map(label => {
            const active = selectedLabels.has(label);
            const color = labelColor(label);
            const description = labelDescriptions.get(label);
            const chip = (
              <button
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
            if (description === undefined) {
              return <Fragment key={label}>{chip}</Fragment>;
            }
            return (
              <Tooltip key={label} label={description} wrap={true}>
                {chip}
              </Tooltip>
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

      {runs.length === 0 && hasActiveFilters ? (
        <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
          <Inbox className="h-8 w-8" />
          <p className="text-sm">No runs match the selected filters</p>
          {baselineTotal !== undefined && baselineTotal > 0 ? (
            <p className="text-[11px]">
              0 of {baselineTotal} runs {baselineLabel}
            </p>
          ) : null}
        </div>
      ) : null}

      {picking ? (
        <div className="mb-3 flex items-center gap-3 rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-xs">
          <span className="font-medium">
            {selectedRunIds.size === 0
              ? "Check the runs to export"
              : `${selectedRunIds.size} selected`}
          </span>
          <button
            type="button"
            onClick={() => replaceSelection(runs.map(run => run.run_id))}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            Select all {runs.length} loaded
          </button>
          {selectedRunIds.size > 0 ? (
            <button
              type="button"
              onClick={clearSelection}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Clear
            </button>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={stopPicking}
              className="inline-flex items-center gap-0.5 text-muted-foreground transition-colors hover:text-foreground"
            >
              <XCircle className="h-3 w-3" />
              Cancel
            </button>
            <button
              type="button"
              disabled={selectedRunIds.size === 0}
              onClick={openExport}
              className="rounded-md bg-foreground px-2 py-0.5 font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
            >
              Export {selectedRunIds.size > 0 ? selectedRunIds.size : ""}
            </button>
          </div>
        </div>
      ) : null}

      <div
        ref={listRef}
        style={{ height: `${groupVirtualizer.getTotalSize()}px`, position: "relative" }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            transform: `translateY(${(groupVirtualizer.getVirtualItems()[0]?.start ?? 0) - listScrollMargin}px)`,
          }}
        >
          {groupVirtualizer.getVirtualItems().map(virtualItem => {
            const group = groups[virtualItem.index];
            if (group === undefined) {
              return null;
            }
            return (
              <div
                key={group.label}
                data-index={virtualItem.index}
                ref={groupVirtualizer.measureElement}
                className="pb-6"
              >
                <h2 className="mb-2 text-sm font-medium text-muted-foreground">{group.label}</h2>
                <div className="rounded-lg border border-border">
                  <table className="w-full table-fixed text-sm">
                    <RunTableColumns picking={picking} />
                    <tbody>
                      {group.runs.map((run, idx) => (
                        <RunRow
                          key={run.run_id}
                          run={run}
                          showTopBorder={idx > 0}
                          onNavigate={navigateToRun}
                          onStop={stopMutation.mutate}
                          onDelete={deleteMutation.mutate}
                          onShowNote={setNoteModalRunId}
                          onConfigPreview={setConfigPreview}
                          shownKnobs={filteredKnobNames}
                          picking={picking}
                          selected={selectedRunIds.has(run.run_id)}
                          onToggleSelected={toggleRunSelected}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      </div>

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
          <p
            className="text-[11px] text-muted-foreground"
            title={
              baselineTotal !== undefined && baselineTotal !== totalRuns
                ? `${totalRuns} of ${baselineTotal} runs ${baselineLabel}`
                : undefined
            }
          >
            Showing {runs.length} of {totalRuns}
            {baselineTotal !== undefined && baselineTotal !== totalRuns
              ? ` / ${baselineTotal}`
              : null}
          </p>
        </div>
      ) : null}
    </div>
  );
}
