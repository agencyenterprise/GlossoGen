import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { useOptionalActiveGroupSlug } from "@/features/auth/group-context";

/**
 * Fetch the group's label glossary from ``GET /labels/descriptions`` and return it
 * as a map from label string to description.
 *
 * Every label-rendering surface calls this to put the description in the chip's
 * hover tooltip; the query key is shared, so they all read one request. A label
 * nobody described is simply absent from the map. Outside any group context (the
 * public ``/demo`` page) the query never fires and the map stays empty.
 */
export function useLabelDescriptions(): Map<string, string> {
  const groupSlug = useOptionalActiveGroupSlug();
  const { data } = useQuery({
    queryKey: ["label-descriptions"],
    enabled: groupSlug !== null,
    queryFn: async () => {
      const { data: resp, error } = await api.GET("/api/g/{group_slug}/labels/descriptions");
      if (error) {
        throw new Error("Failed to fetch label descriptions");
      }
      return resp;
    },
  });
  return useMemo(
    () => new Map((data?.descriptions ?? []).map(entry => [entry.label, entry.description])),
    [data]
  );
}
