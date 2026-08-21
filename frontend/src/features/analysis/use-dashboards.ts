"use client";

/**
 * Reading and writing saved dashboards.
 *
 * Every mutation invalidates the list, so a save shows up in the sidebar without a
 * reload. The server's `detail` carries the one refusal worth reading out loud: a name
 * this group already uses.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { apiError } from "@/shared/lib/api-error";
import type { components } from "@/types/api.gen";

export type Dashboard = components["schemas"]["Dashboard"];
export type DashboardContent = components["schemas"]["DashboardContent"];
export type DashboardSummary = components["schemas"]["DashboardSummary"];
export type ChartSpec = components["schemas"]["ChartSpec"];
export type ChartKind = components["schemas"]["ChartKind"];
export type ChartEncoding = components["schemas"]["ChartEncoding"];

const DASHBOARDS_KEY = ["dashboards"];

/** The cache key one dashboard's fetch is held under. */
export function dashboardKey(dashboardId: string): string[] {
  return [...DASHBOARDS_KEY, dashboardId];
}

export function useDashboardList() {
  return useQuery({
    queryKey: DASHBOARDS_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/dashboards");
      if (error) {
        throw apiError(error, "Could not list dashboards");
      }
      return data;
    },
  });
}

export function useDashboard(dashboardId: string | null) {
  return useQuery({
    queryKey: dashboardKey(dashboardId ?? ""),
    enabled: dashboardId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/dashboards/{dashboard_id}", {
        params: { path: { dashboard_id: dashboardId ?? "" } },
      });
      if (error) {
        throw apiError(error, "Could not open that dashboard");
      }
      return data;
    },
  });
}

export function useSaveDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      dashboardId,
      content,
    }: {
      dashboardId: string | null;
      content: DashboardContent;
    }) => {
      if (dashboardId === null) {
        const { data, error } = await api.POST("/api/g/{group_slug}/dashboards", {
          body: content,
        });
        if (error) {
          throw apiError(error, "Could not save this dashboard");
        }
        return data;
      }
      const { data, error } = await api.PUT("/api/g/{group_slug}/dashboards/{dashboard_id}", {
        params: { path: { dashboard_id: dashboardId } },
        body: content,
      });
      if (error) {
        throw apiError(error, "Could not save this dashboard");
      }
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DASHBOARDS_KEY });
    },
  });
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dashboardId: string) => {
      const { error } = await api.DELETE("/api/g/{group_slug}/dashboards/{dashboard_id}", {
        params: { path: { dashboard_id: dashboardId } },
      });
      if (error) {
        throw apiError(error, "Could not delete this dashboard");
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DASHBOARDS_KEY });
    },
  });
}
