"use client";

import { UserCog } from "lucide-react";
import Link from "next/link";

interface ReplaceAgentBadgeProps {
  sourceRunId: string;
  replacedAgentId: string;
  replacementModel: string;
  roundStart: number;
}

export function ReplaceAgentBadge({
  sourceRunId,
  replacedAgentId,
  replacementModel,
  roundStart,
}: ReplaceAgentBadgeProps) {
  return (
    <Link
      href={`/runs/${sourceRunId}`}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      title={`Replaced ${replacedAgentId} with ${replacementModel} from start of round ${roundStart} (source: ${sourceRunId})`}
    >
      <UserCog className="h-3 w-3" />
      <span>
        Replaced <span className="font-medium">{replacedAgentId}</span>
        {" → "}
        <span className="font-medium">{replacementModel}</span>
        {" @ round "}
        {roundStart}
      </span>
    </Link>
  );
}
