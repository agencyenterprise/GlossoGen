"use client";

import { RotateCcw } from "lucide-react";
import Link from "next/link";

interface ResumeAtRoundBadgeProps {
  sourceRunId: string;
  roundStart: number;
  roundsAfterResume: number;
}

export function ResumeAtRoundBadge({
  sourceRunId,
  roundStart,
  roundsAfterResume,
}: ResumeAtRoundBadgeProps) {
  return (
    <Link
      href={`/runs/${sourceRunId}`}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      title={`Resumed from start of round ${roundStart}, played ${roundsAfterResume} round${
        roundsAfterResume === 1 ? "" : "s"
      } after (source: ${sourceRunId})`}
    >
      <RotateCcw className="h-3 w-3" />
      <span>
        Resumed @ round <span className="font-medium">{roundStart}</span>
        {" (+"}
        {roundsAfterResume}
        {")"}
      </span>
    </Link>
  );
}
