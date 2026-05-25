"use client";

import { ArrowLeftRight, GitFork, UserCog, UserPlus } from "lucide-react";
import Link from "next/link";
import { useGroupPath } from "@/features/auth/group-context";

interface ForkBadgeProps {
  sourceRunId: string;
  targetMessageId: string;
}

export function ForkBadge({ sourceRunId, targetMessageId: _targetMessageId }: ForkBadgeProps) {
  const groupPath = useGroupPath();
  return (
    <Link
      href={groupPath(`/runs/${sourceRunId}`)}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <GitFork className="h-3 w-3" />
      <span>
        Forked from <span className="font-medium">{sourceRunId.slice(0, 8)}</span>
      </span>
    </Link>
  );
}

const STACK_BOTTOM_CLASSES = [
  "bottom-6",
  "bottom-20",
  "bottom-34",
  "bottom-48",
  "bottom-62",
  "bottom-76",
  "bottom-90",
  "bottom-104",
] as const;

function bottomClass(stackIndex: number): string {
  const clamped = Math.min(Math.max(stackIndex, 0), STACK_BOTTOM_CLASSES.length - 1);
  const cls = STACK_BOTTOM_CLASSES[clamped];
  return cls ?? STACK_BOTTOM_CLASSES[0]!;
}

interface ForkPointFabProps {
  onClick: () => void;
  stackIndex: number;
}

/** Floating action button that scrolls to the fork point message. */
export function ForkPointFab({ onClick, stackIndex }: ForkPointFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-blue-300/60 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 shadow-lg transition-all hover:bg-blue-100 hover:shadow-xl dark:border-blue-700/50 dark:bg-blue-950/80 dark:text-blue-300 dark:hover:bg-blue-900/80`}
      title="Go to fork point"
    >
      <GitFork className="h-3.5 w-3.5" />
      Go to edited message
    </button>
  );
}

interface SwapPointFabProps {
  onClick: () => void;
  roundNumber: number;
  stackIndex: number;
}

/** Floating action button that scrolls to the first post-swap message. */
export function SwapPointFab({ onClick, roundNumber, stackIndex }: SwapPointFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 shadow-lg transition-all hover:bg-amber-100 hover:shadow-xl dark:border-amber-700/50 dark:bg-amber-950/80 dark:text-amber-300 dark:hover:bg-amber-900/80`}
      title={`Go to observer swap (round ${roundNumber})`}
    >
      <ArrowLeftRight className="h-3.5 w-3.5" />
      Go to swap (round {roundNumber})
    </button>
  );
}

interface InternJoinFabProps {
  onClick: () => void;
  roundNumber: number;
  stackIndex: number;
}

/** Floating action button that scrolls to the intern-join marker. */
export function InternJoinFab({ onClick, roundNumber, stackIndex }: InternJoinFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-emerald-300/60 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 shadow-lg transition-all hover:bg-emerald-100 hover:shadow-xl dark:border-emerald-700/50 dark:bg-emerald-950/80 dark:text-emerald-300 dark:hover:bg-emerald-900/80`}
      title={`Go to intern join (round ${roundNumber})`}
    >
      <UserPlus className="h-3.5 w-3.5" />
      Go to intern join (round {roundNumber})
    </button>
  );
}

interface InternTakeoverFabProps {
  onClick: () => void;
  roundNumber: number;
  stackIndex: number;
}

/** Floating action button that scrolls to the intern-takeover marker. */
export function InternTakeoverFab({ onClick, roundNumber, stackIndex }: InternTakeoverFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-violet-300/60 bg-violet-50 px-3 py-2 text-xs font-medium text-violet-700 shadow-lg transition-all hover:bg-violet-100 hover:shadow-xl dark:border-violet-700/50 dark:bg-violet-950/80 dark:text-violet-300 dark:hover:bg-violet-900/80`}
      title={`Go to intern takeover (round ${roundNumber})`}
    >
      <UserCog className="h-3.5 w-3.5" />
      Go to intern takeover (round {roundNumber})
    </button>
  );
}

interface ReplaceAgentPointFabProps {
  onClick: () => void;
  roundNumber: number;
  stackIndex: number;
}

/** Floating action button that scrolls to the replace-agent marker. */
export function ReplaceAgentPointFab({
  onClick,
  roundNumber,
  stackIndex,
}: ReplaceAgentPointFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-sky-300/60 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700 shadow-lg transition-all hover:bg-sky-100 hover:shadow-xl dark:border-sky-700/50 dark:bg-sky-950/80 dark:text-sky-300 dark:hover:bg-sky-900/80`}
      title={`Go to agent replacement (round ${roundNumber})`}
    >
      <UserCog className="h-3.5 w-3.5" />
      Go to agent replacement (round {roundNumber})
    </button>
  );
}

interface AgentSwapPointFabProps {
  onClick: () => void;
  roundNumber: number;
  agentId: string;
  stackIndex: number;
}

/** Floating action button that scrolls to a scheduled-events in-run agent swap. */
export function AgentSwapPointFab({
  onClick,
  roundNumber,
  agentId,
  stackIndex,
}: AgentSwapPointFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-indigo-300/60 bg-indigo-50 px-3 py-2 text-xs font-medium text-indigo-700 shadow-lg transition-all hover:bg-indigo-100 hover:shadow-xl dark:border-indigo-700/50 dark:bg-indigo-950/80 dark:text-indigo-300 dark:hover:bg-indigo-900/80`}
      title={`Go to ${agentId} swap (round ${roundNumber})`}
    >
      <UserCog className="h-3.5 w-3.5" />
      Go to {agentId} swap (r{roundNumber})
    </button>
  );
}

interface CrossRunReplaceAgentPointFabProps {
  onClick: () => void;
  roundNumber: number;
  stackIndex: number;
}

/** Floating action button that scrolls to the cross-run replace-agent marker. */
export function CrossRunReplaceAgentPointFab({
  onClick,
  roundNumber,
  stackIndex,
}: CrossRunReplaceAgentPointFabProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed ${bottomClass(stackIndex)} right-6 z-40 flex items-center gap-1.5 rounded-full border border-violet-300/60 bg-violet-50 px-3 py-2 text-xs font-medium text-violet-700 shadow-lg transition-all hover:bg-violet-100 hover:shadow-xl dark:border-violet-700/50 dark:bg-violet-950/80 dark:text-violet-300 dark:hover:bg-violet-900/80`}
      title={`Go to cross-run agent import (round ${roundNumber})`}
    >
      <UserCog className="h-3.5 w-3.5" />
      Go to cross-run import (round {roundNumber})
    </button>
  );
}
