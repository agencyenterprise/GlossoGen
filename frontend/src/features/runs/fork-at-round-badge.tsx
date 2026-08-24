"use client";

import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useGroupPath } from "@/features/auth/group-context";

interface ForkAtRoundBadgeProps {
  sourceRunId: string;
  afterRound: number;
  roundsAfter: number;
}

export function ForkAtRoundBadge({ sourceRunId, afterRound, roundsAfter }: ForkAtRoundBadgeProps) {
  const groupPath = useGroupPath();
  return (
    <Link
      href={groupPath(`/runs/${sourceRunId}`)}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      title={`Forked after round ${afterRound}, played ${roundsAfter} round${
        roundsAfter === 1 ? "" : "s"
      } after (source: ${sourceRunId})`}
    >
      <RotateCcw className="h-3 w-3" />
      <span>
        Forked after round <span className="font-medium">{afterRound}</span>
        {" (+"}
        {roundsAfter}
        {")"}
      </span>
    </Link>
  );
}
