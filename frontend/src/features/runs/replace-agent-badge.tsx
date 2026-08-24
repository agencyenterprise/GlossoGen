"use client";

import { UserCog } from "lucide-react";
import Link from "next/link";
import { useGroupPath } from "@/features/auth/group-context";

interface ReplaceAgentBadgeProps {
  sourceRunId: string;
  replacedAgentId: string;
  replacementModel: string;
  afterRound: number;
}

export function ReplaceAgentBadge({
  sourceRunId,
  replacedAgentId,
  replacementModel,
  afterRound,
}: ReplaceAgentBadgeProps) {
  const groupPath = useGroupPath();
  return (
    <Link
      href={groupPath(`/runs/${sourceRunId}`)}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      title={`Replaced ${replacedAgentId} with ${replacementModel} after round ${afterRound} (source: ${sourceRunId})`}
    >
      <UserCog className="h-3 w-3" />
      <span>
        Replaced <span className="font-medium">{replacedAgentId}</span>
        {" → "}
        <span className="font-medium">{replacementModel}</span>
        {" after round "}
        {afterRound}
      </span>
    </Link>
  );
}
