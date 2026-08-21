"use client";

/**
 * Reading the analysis endpoints.
 *
 * Both are POSTs inside read hooks, for the reason the export preview is: the body
 * carries a selection that can name hundreds of runs, which does not fit in a URL.
 * React Query does not care about the verb, and the selection is part of the query
 * key, so flipping a filter refetches and flipping it back is instant.
 *
 * The server's own `detail` is surfaced verbatim. It says things like "this selection
 * is 6000 runs, the limit is 5000", and replacing that with a generic message would
 * leave the reader with nothing to act on.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { apiError } from "@/shared/lib/api-error";
import type { components } from "@/types/api.gen";

export type RunSelection =
  components["schemas"]["FilterRunSelection"] | components["schemas"]["ExplicitRunSelection"];
export type AnalysisGrain = components["schemas"]["AnalysisGrain"];
export type AnalysisQuerySpec = components["schemas"]["AnalysisQuerySpec"];
export type AnalysisResult = components["schemas"]["AnalysisResult"];
export type AnalysisFieldCatalog = components["schemas"]["AnalysisFieldCatalog"];
export type AnalysisDimension = components["schemas"]["AnalysisDimension"];
export type AnalysisMeasureField = components["schemas"]["AnalysisMeasureField"];
export type DimensionFilter = components["schemas"]["DimensionFilter"];
export type MeasureSpec = components["schemas"]["MeasureSpec"];

/** What a selection can be grouped, filtered, and measured by at one grain. */
export function useAnalysisFields({
  selection,
  grain,
  enabled,
}: {
  selection: RunSelection;
  grain: AnalysisGrain;
  enabled: boolean;
}) {
  return useQuery({
    queryKey: ["analysis-fields", selection, grain],
    enabled,
    staleTime: 30_000,
    queryFn: async () => {
      const { data, error } = await api.POST("/api/g/{group_slug}/runs/analysis/fields", {
        body: { selection, grain },
      });
      if (error) {
        throw apiError(error, "Could not describe this selection");
      }
      return data;
    },
  });
}

/** One grouped, aggregated answer. */
export function useAnalysisQuery({
  selection,
  query,
  enabled,
}: {
  selection: RunSelection;
  query: AnalysisQuerySpec;
  enabled: boolean;
}) {
  return useQuery({
    queryKey: ["analysis-query", selection, query],
    enabled,
    staleTime: 30_000,
    queryFn: async () => {
      const { data, error } = await api.POST("/api/g/{group_slug}/runs/analysis/query", {
        body: { selection, query },
      });
      if (error) {
        throw apiError(error, "Could not answer this query");
      }
      return data;
    },
  });
}
