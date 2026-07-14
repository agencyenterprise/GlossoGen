"use client";

import { useQuery } from "@tanstack/react-query";
import { GitFork, Inbox, Loader2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import { formatCost, formatDuration, formatTime, humanize } from "../runs/format";

type RunStatus = components["schemas"]["RunStatus"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  starting: "Starting",
  error: "Error",
  killed: "Killed",
};

export function BranchesList() {
  const router = useRouter();
  const groupPath = useGroupPath();

  const { data, isLoading, error } = useQuery({
    queryKey: ["branches"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/branches", {});
      if (error) {
        throw new Error("Failed to fetch branches");
      }
      return data;
    },
  });

  const sourceEntries = data?.sources ?? [];

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

  if (sourceEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-muted-foreground">
        <Inbox className="h-10 w-10" />
        <p>No forked runs found</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30 text-left text-xs font-medium text-muted-foreground">
            <th className="py-2 pl-4">Scenario</th>
            <th className="px-3 py-2">Model</th>
            <th className="px-3 py-2 text-right">Messages</th>
            <th className="px-3 py-2 text-right">Cost</th>
            <th className="px-3 py-2 text-right">Duration</th>
            <th className="px-3 py-2 text-right">Time</th>
            <th className="px-3 py-2 text-right">Status</th>
            <th className="px-3 py-2 text-right">Forks</th>
          </tr>
        </thead>
        <tbody>
          {sourceEntries.map((entry, idx) => {
            const run = entry.source_run;
            const borderClass = idx > 0 ? "border-t border-border" : "";
            return (
              <tr
                key={run.run_id}
                className={`group cursor-pointer transition-colors hover:bg-accent/50 ${borderClass}`}
                onClick={() => {
                  router.push(groupPath(`/branches/${run.run_id}`));
                }}
              >
                <td className="whitespace-nowrap py-2 pl-4 font-medium">
                  {humanize(run.scenario_name)}
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
                  {run.duration_seconds > 0 ? formatDuration(run.duration_seconds) : "—"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
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
                <td className="whitespace-nowrap px-3 py-2 pr-4 text-right">
                  <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                    <GitFork className="h-3 w-3" />
                    {entry.derived_count}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
