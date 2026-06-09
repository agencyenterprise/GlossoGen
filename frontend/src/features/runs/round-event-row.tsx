"use client";

import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Flag, Inbox, XCircle } from "lucide-react";
import type { components } from "@/types/api.gen";
import { cn } from "@/shared/lib/cn";
import { humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type RoundResult = components["schemas"]["RoundResult"];
type RoundInjection = components["schemas"]["RoundInjection"];

/** Groups injections sharing identical text and lists the recipient role names. */
interface InjectionGroup {
  text: string;
  recipients: string[];
}

function groupInjectionsByText(
  injections: RoundInjection[],
  roleNameForAgent: (agentId: string) => string
): InjectionGroup[] {
  const byText = new Map<string, string[]>();
  for (const injection of injections) {
    const recipients = byText.get(injection.text);
    const roleName = roleNameForAgent(injection.agent_id);
    if (recipients) {
      if (!recipients.includes(roleName)) {
        recipients.push(roleName);
      }
    } else {
      byText.set(injection.text, [roleName]);
    }
  }
  return Array.from(byText.entries()).map(([text, recipients]) => ({ text, recipients }));
}

interface RoundInjectionRowProps {
  injections: RoundInjection[];
  roleNameForAgent: (agentId: string) => string;
}

/** Inline event row for scenario injections delivered at the start of a round.
 *  Identical injection texts are collapsed into one row listing every recipient
 *  role. The injection body is expandable. */
export function RoundInjectionRow({ injections, roleNameForAgent }: RoundInjectionRowProps) {
  const groups = groupInjectionsByText(injections, roleNameForAgent);
  if (groups.length === 0) {
    return null;
  }
  return (
    <div className="mx-4 my-1.5 flex flex-col gap-1.5">
      {groups.map((group, idx) => (
        <InjectionEntry key={idx} group={group} />
      ))}
    </div>
  );
}

function InjectionEntry({ group }: { group: InjectionGroup }) {
  const [expanded, setExpanded] = useState(false);
  const ChevronIcon = expanded ? ChevronDown : ChevronRight;
  return (
    <div className="rounded-md border border-amber-300/60 bg-amber-50/50 px-2.5 py-1.5 text-[11px] dark:border-amber-800/40 dark:bg-amber-950/20">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center gap-1.5 text-left"
      >
        <Inbox className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="font-medium text-amber-700 dark:text-amber-300">Injection</span>
        <span className="truncate text-amber-700/70 dark:text-amber-300/70">
          → {group.recipients.join(", ")}
        </span>
        <ChevronIcon className="ml-auto h-3 w-3 shrink-0 text-amber-600/60 dark:text-amber-400/60" />
      </button>
      <ProseMarkdown
        className={cn(
          "mt-1 text-amber-900/80 dark:text-amber-200/80",
          !expanded && "line-clamp-2 **:my-0! **:inline [&_br]:hidden"
        )}
      >
        {group.text}
      </ProseMarkdown>
    </div>
  );
}

interface RoundOutcomeRowProps {
  results: RoundResult[];
  trigger: string | null;
}

/** Inline event row summarizing how a round ended: the per-team pass/fail
 *  result (from RoundResultRecorded) and the round-end trigger. */
export function RoundOutcomeRow({ results, trigger }: RoundOutcomeRowProps) {
  if (results.length === 0 && trigger === null) {
    return null;
  }
  return (
    <div className="mx-4 my-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
      {results.map((result, idx) => (
        <ResultPill key={idx} result={result} />
      ))}
      {trigger !== null ? (
        <span className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 px-2 py-0.5 text-muted-foreground">
          <Flag className="h-3 w-3 shrink-0" />
          ended: {humanize(trigger)}
        </span>
      ) : null}
    </div>
  );
}

function ResultPill({ result }: { result: RoundResult }) {
  const Icon = result.success ? CheckCircle2 : XCircle;
  const teamLabel = result.team_id !== null ? `${humanize(result.team_id)}: ` : "";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5",
        result.success
          ? "border-emerald-300/60 bg-emerald-50/60 text-emerald-700 dark:border-emerald-800/40 dark:bg-emerald-950/30 dark:text-emerald-300"
          : "border-red-300/60 bg-red-50/60 text-red-700 dark:border-red-800/40 dark:bg-red-950/30 dark:text-red-300"
      )}
      title={result.reason}
    >
      <Icon className="h-3 w-3 shrink-0" />
      {teamLabel}
      {result.success ? "pass" : "fail"}
    </span>
  );
}
