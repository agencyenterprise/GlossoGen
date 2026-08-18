"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { components } from "@/types/api.gen";

type FilterRunSelection = components["schemas"]["FilterRunSelection"];

/**
 * The filter half of a selection, without its discriminator.
 *
 * Deriving it from the generated model rather than restating it means adding a
 * filter on the backend fails the typecheck here until this publishes it.
 */
export type RunExportFilters = Omit<FilterRunSelection, "kind">;

interface RunExportSelectionValue {
  /** True while the export modal is open. Two things open it, so it lives here. */
  exportOpen: boolean;
  openExport: () => void;
  closeExport: () => void;
  /** True while the list is showing checkboxes for picking runs. */
  picking: boolean;
  startPicking: () => void;
  stopPicking: () => void;
  selectedRunIds: ReadonlySet<string>;
  toggleRunSelected: (runId: string) => void;
  replaceSelection: (runIds: string[]) => void;
  clearSelection: () => void;
  filters: RunExportFilters;
  publishFilters: (filters: RunExportFilters) => void;
  matchingRunCount: number;
  publishMatchingRunCount: (count: number) => void;
}

const EMPTY_FILTERS: RunExportFilters = {
  scenario: [],
  labels: [],
  run_id_contains: null,
  // The runs list offers no control for these two, so it never narrows by them.
  // They exist on the wire because a scripted caller can.
  status: null,
  contains_agent_id: null,
};

const RunExportSelectionContext = createContext<RunExportSelectionValue | null>(null);

/**
 * Holds whether the list is in picking mode, which runs are checked, and the filters
 * the list is currently showing.
 *
 * A context and not props, because the consumers sit at opposite ends of the tree:
 * the Export button in the page toolbar, and a checkbox on every row inside a
 * virtualized table.
 *
 * Picking is a mode rather than a permanent column. Checkboxes on every row all the
 * time are a cost paid by everyone browsing runs for a feature few of them are using
 * at that moment, so the export asks for them when it needs them.
 */
export function RunExportSelectionProvider({ children }: { children: React.ReactNode }) {
  const [exportOpen, setExportOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [selectedRunIds, setSelectedRunIds] = useState<ReadonlySet<string>>(new Set());
  const [filters, setFilters] = useState<RunExportFilters>(EMPTY_FILTERS);
  const [matchingRunCount, setMatchingRunCount] = useState(0);

  // These three are referentially stable for the life of the provider, which is
  // what keeps a single checkbox click from re-rendering every mounted row: the
  // rows are memoized on their props, and an unstable callback would defeat that.
  const toggleRunSelected = useCallback((runId: string) => {
    setSelectedRunIds(current => {
      const next = new Set(current);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  }, []);

  const replaceSelection = useCallback((runIds: string[]) => {
    setSelectedRunIds(new Set(runIds));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedRunIds(new Set());
  }, []);

  const openExport = useCallback(() => {
    setExportOpen(true);
  }, []);

  const closeExport = useCallback(() => {
    setExportOpen(false);
  }, []);

  // Picking happens in the list, so the modal steps out of the way for it.
  const startPicking = useCallback(() => {
    setPicking(true);
    setExportOpen(false);
  }, []);

  // Leaving the mode drops the selection: the checkboxes that built it are gone, so
  // a count with no way to see what is in it would be worse than nothing.
  const stopPicking = useCallback(() => {
    setPicking(false);
    setSelectedRunIds(new Set());
  }, []);

  const value = useMemo(
    () => ({
      exportOpen,
      openExport,
      closeExport,
      picking,
      startPicking,
      stopPicking,
      selectedRunIds,
      toggleRunSelected,
      replaceSelection,
      clearSelection,
      filters,
      publishFilters: setFilters,
      matchingRunCount,
      publishMatchingRunCount: setMatchingRunCount,
    }),
    [
      exportOpen,
      openExport,
      closeExport,
      picking,
      startPicking,
      stopPicking,
      selectedRunIds,
      toggleRunSelected,
      replaceSelection,
      clearSelection,
      filters,
      matchingRunCount,
    ]
  );

  return (
    <RunExportSelectionContext.Provider value={value}>
      {children}
    </RunExportSelectionContext.Provider>
  );
}

export function useRunExportSelection(): RunExportSelectionValue {
  const value = useContext(RunExportSelectionContext);
  if (value === null) {
    throw new Error("useRunExportSelection must be used inside a RunExportSelectionProvider");
  }
  return value;
}
