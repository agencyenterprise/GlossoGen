"use client";

import { Users } from "lucide-react";
import Link from "next/link";
import { useGroupPath } from "@/features/auth/group-context";

interface CrossRunReplaceAgentBadgeProps {
  sourceARunId: string;
  sourceBRunId: string;
  replacedAgentId: string;
  importedModel: string;
  roundStart: number;
  sourceBRoundEnd: number;
}

export function CrossRunReplaceAgentBadge({
  sourceARunId,
  sourceBRunId,
  replacedAgentId,
  importedModel,
  roundStart,
  sourceBRoundEnd,
}: CrossRunReplaceAgentBadgeProps) {
  const groupPath = useGroupPath();
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground"
      title={`Imported ${replacedAgentId} from ${sourceBRunId} (through end of round ${sourceBRoundEnd}) into ${sourceARunId} at start of round ${roundStart}`}
    >
      <Users className="h-3 w-3" />
      <span>Cross-run </span>
      <span className="font-medium">{replacedAgentId}</span>
      <span>: A=</span>
      <Link
        href={groupPath(`/runs/${sourceARunId}`)}
        className="font-medium underline-offset-2 hover:text-foreground hover:underline"
      >
        {sourceARunId}
      </Link>
      <span>· B=</span>
      <Link
        href={groupPath(`/runs/${sourceBRunId}`)}
        className="font-medium underline-offset-2 hover:text-foreground hover:underline"
      >
        {sourceBRunId}
      </Link>
      <span>
        {" @ round "}
        {roundStart}
        {" / src B end "}
        {sourceBRoundEnd}
        {" → "}
      </span>
      <span className="font-medium">{importedModel}</span>
    </span>
  );
}
