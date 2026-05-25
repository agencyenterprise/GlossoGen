"use client";

import { GitFork } from "lucide-react";
import Link from "next/link";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import { formatTime } from "../runs/format";

type RunStatus = components["schemas"]["RunStatus"];

const STATUS_LABELS: Record<RunStatus, string> = {
  scenario_complete: "Completed",
  in_progress: "In Progress",
  starting: "Starting",
  error: "Error",
  killed: "Killed",
};

export interface ForkInfo {
  runId: string;
  status: RunStatus;
  timestamp: string;
  models: string[];
}

interface ForkBranchCardProps {
  forks: ForkInfo[];
  targetMessageId: string;
}

/** Renders fork indicators on the right side of the timeline trunk. */
export function ForkBranchCard({ forks, targetMessageId }: ForkBranchCardProps) {
  const groupPath = useGroupPath();
  return (
    <div className="rounded-md border border-violet-200 bg-violet-50/60 dark:border-violet-800/50 dark:bg-violet-950/30">
      {forks.map(fork => (
        <Link
          key={fork.runId}
          href={groupPath(`/runs/${fork.runId}?highlight=${targetMessageId}`)}
          className="flex items-center gap-2 px-3 py-1.5 text-xs transition-colors first:rounded-t-md last:rounded-b-md hover:bg-violet-100/80 dark:hover:bg-violet-900/40"
        >
          <GitFork className="h-3 w-3 shrink-0 text-violet-600 dark:text-violet-400" />
          <span className="font-mono text-violet-700 dark:text-violet-300">
            {fork.runId.split("/").pop()}
          </span>
          <span
            className={`text-[10px] font-medium ${
              fork.status === "in_progress"
                ? "text-green-600 dark:text-green-400"
                : fork.status === "error"
                  ? "text-red-600 dark:text-red-400"
                  : "text-muted-foreground"
            }`}
          >
            {STATUS_LABELS[fork.status] ?? fork.status}
          </span>
          <span className="text-muted-foreground">{formatTime(fork.timestamp)}</span>
        </Link>
      ))}
    </div>
  );
}
