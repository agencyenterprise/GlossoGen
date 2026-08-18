"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { components } from "@/types/api.gen";

type RunSelection =
  components["schemas"]["FilterRunSelection"] | components["schemas"]["ExplicitRunSelection"];

/** Read the FastAPI ``detail`` off an error payload, or null if it carries none. */
function detailOf(error: unknown): string | null {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return null;
}

/**
 * Describe what a selection would export.
 *
 * A POST inside a read hook, because the selection is too large to put in a URL:
 * an explicit list can carry hundreds of run ids. React Query does not care about
 * the verb, and the alternative would mean reimplementing its caching by hand.
 *
 * The selection object is part of the query key, so flipping a filter refetches
 * and flipping it back is instant.
 */
export function useExportPreview({
  selection,
  includeRawSizeEstimate,
  includeLogs,
  enabled,
}: {
  selection: RunSelection;
  includeRawSizeEstimate: boolean;
  includeLogs: boolean;
  enabled: boolean;
}) {
  return useQuery({
    queryKey: ["run-export-preview", selection, includeRawSizeEstimate, includeLogs],
    enabled,
    staleTime: 30_000,
    queryFn: async () => {
      const { data, error } = await api.POST("/api/g/{group_slug}/runs/export/preview", {
        body: {
          selection,
          include_raw_size_estimate: includeRawSizeEstimate,
          include_logs: includeLogs,
        },
      });
      if (error) {
        // The server says what was wrong with the selection; a generic message here
        // would replace "this selection is 3580 runs, the limit is 5000" with nothing.
        throw new Error(detailOf(error) ?? "Could not describe this export");
      }
      return data;
    },
  });
}
