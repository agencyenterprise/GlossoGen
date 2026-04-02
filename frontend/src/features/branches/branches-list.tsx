"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitFork, Inbox, Loader2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import type { components } from "@/types/api.gen";
import { formatCost, formatDuration, formatTime, humanize } from "../runs/format";

type RunSummary = components["schemas"]["RunSummary"];
type RunStatus = components["schemas"]["RunStatus"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  error: "Error",
};

interface SourceRunEntry {
  sourceRun: RunSummary;
  forks: RunSummary[];
}

export function BranchesList() {
  const router = useRouter();

  const { data, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs");
      if (error) {
        throw new Error("Failed to fetch runs");
      }
      return data;
    },
  });

  const sourceEntries = useMemo(() => {
    if (!data) {
      return [];
    }
    const runsById = new Map<string, RunSummary>();
    for (const run of data.runs) {
      runsById.set(run.run_id, run);
    }

    const forksBySource = new Map<string, RunSummary[]>();
    for (const run of data.runs) {
      if (!run.fork_source) {
        continue;
      }
      const sourceId = run.fork_source.source_run_id;
      const existing = forksBySource.get(sourceId);
      if (existing) {
        existing.push(run);
      } else {
        forksBySource.set(sourceId, [run]);
      }
    }

    const entries: SourceRunEntry[] = [];
    for (const [sourceId, forks] of forksBySource) {
      const sourceRun = runsById.get(sourceId);
      if (!sourceRun) {
        continue;
      }
      entries.push({ sourceRun, forks });
    }

    entries.sort((a, b) => b.sourceRun.timestamp.localeCompare(a.sourceRun.timestamp));
    return entries;
  }, [data]);

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
            const run = entry.sourceRun;
            const borderClass = idx > 0 ? "border-t border-border" : "";
            return (
              <tr
                key={run.run_id}
                className={`group cursor-pointer transition-colors hover:bg-accent/50 ${borderClass}`}
                onClick={() => {
                  router.push(`/branches/${run.run_id}`);
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
                    {entry.forks.length}
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
