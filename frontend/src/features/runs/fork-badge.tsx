"use client";

import { GitFork } from "lucide-react";
import Link from "next/link";

interface ForkBadgeProps {
  sourceRunId: string;
  targetMessageId: string;
}

export function ForkBadge({ sourceRunId, targetMessageId: _targetMessageId }: ForkBadgeProps) {
  return (
    <Link
      href={`/runs/${sourceRunId}`}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <GitFork className="h-3 w-3" />
      <span>
        Forked from <span className="font-medium">{sourceRunId.slice(0, 8)}</span>
      </span>
    </Link>
  );
}

interface ForkPointFabProps {
  onClick: () => void;
}

/** Floating action button that scrolls to the fork point message. */
export function ForkPointFab({ onClick }: ForkPointFabProps) {
  return (
    <button
      onClick={onClick}
      className="fixed bottom-6 right-6 z-40 flex items-center gap-1.5 rounded-full border border-blue-300/60 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 shadow-lg transition-all hover:bg-blue-100 hover:shadow-xl dark:border-blue-700/50 dark:bg-blue-950/80 dark:text-blue-300 dark:hover:bg-blue-900/80"
      title="Go to fork point"
    >
      <GitFork className="h-3.5 w-3.5" />
      Go to edited message
    </button>
  );
}
