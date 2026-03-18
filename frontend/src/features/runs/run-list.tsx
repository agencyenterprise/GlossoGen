"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Inbox, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import type { components } from "@/types/api.gen";
import { formatTime, humanize } from "./format";

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

type EndReason = components["schemas"]["EndReason"];

const END_REASON_LABELS: Record<EndReason, string> = {
  scenario_complete: "Scenario Completed",
  error: "Error",
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

  const runs = data!.runs;

  if (runs.length === 0) {
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
      {groups.map(group => (
        <div key={group.label}>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{group.label}</h2>
          <div className="divide-y divide-border rounded-lg border border-border">
            {group.runs.map(run => (
              <Link
                key={run.run_id}
                href={`/runs/${run.run_id}`}
                className="flex items-center gap-6 px-4 py-2.5 text-sm transition-colors hover:bg-accent/50"
              >
                <span className="w-40 font-medium">{humanize(run.scenario_name)}</span>
                <span className="w-20 text-muted-foreground">{formatTime(run.timestamp)}</span>
                <span className="w-16 text-muted-foreground">{run.total_turns} turns</span>
                <span className="w-36 text-muted-foreground">
                  {END_REASON_LABELS[run.end_reason] ?? run.end_reason}
                </span>
                <span className="ml-auto">
                  {run.has_evaluation ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      <CheckCircle className="h-3 w-3" />
                      Evaluated
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                      No evaluation
                    </span>
                  )}
                </span>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
