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
