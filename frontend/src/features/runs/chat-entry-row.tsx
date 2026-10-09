"use client";

import { memo, type RefObject } from "react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import type { ChatRow } from "./chat-rows";
import { formatTime } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { NotificationDisplay } from "./notification-display";
import { ToolCallDisplay } from "./tool-call-display";
import { RunCycleFailureDisplay } from "./run-cycle-failure-display";

type AgentDetail = components["schemas"]["AgentDetail"];

/** Renders either the notification chip (for split notification-result entries)
 *  or the generic tool-call pill. The split between read_notifications call and
 *  its response happens upstream in mergeEntries; here we only pick a renderer. */
function ToolOrNotification({ entry }: { entry: DisplayEntry }) {
  if (entry.is_notification_result) {
    if (entry.notification_display !== null) {
      return entry.notification_display;
    }
    return <NotificationDisplay result={entry.tool_result} />;
  }
  return (
    <ToolCallDisplay
      toolName={entry.tool_name}
      arguments={entry.tool_arguments}
      result={entry.tool_result}
      judgeMetadata={entry.judge_metadata}
      toolMetadata={entry.tool_metadata}
    />
  );
}

interface ChatEntryRowProps {
  row: Extract<ChatRow, { kind: "entry" }>;
  agent: AgentDetail | undefined;
  color: AgentColor | undefined;
  entryChColor: AgentColor | undefined;
  isPreResume: boolean;
  showChannelBadge: boolean;
  isLinkHovered: boolean;
  forkPointMessageId: string | null;
  messageRefs: RefObject<Map<string, HTMLDivElement>>;
  onSelectAgent: (agentId: string) => void;
  setHoveredCallId: (callId: string | null) => void;
  jumpToMessage: (messageId: string) => void;
}

export const ChatEntryRow = memo(function ChatEntryRow({
  row,
  agent,
  color,
  entryChColor,
  isPreResume,
  showChannelBadge,
  isLinkHovered,
  forkPointMessageId,
  messageRefs,
  onSelectAgent,
  setHoveredCallId,
  jumpToMessage,
}: ChatEntryRowProps) {
  const entry = row.entry;
  const displayText = entry.text;
  const hasLinkedPair = entry.paired_message_id !== "";
  const { turn } = row;
  // Prefer a display name only when it differs from the agent_id:
  // legacy runs (recorded before sender_display_name existed) backfill
  // it with the raw agent_id, so fall through to the role name there.
  // Scenarios that rotate identity behind one agent_id still get their
  // distinct display name.
  const turnDisplayName = turn.displayName ?? agent?.role_name ?? turn.agentId;

  return (
    <div
      className={cn(
        "flex gap-2.5 px-4 py-1 transition-colors hover:bg-muted/50",
        isPreResume && "opacity-50"
      )}
    >
      <div className="flex w-7 shrink-0 flex-col items-start">
        {row.isTurnStart ? (
          <>
            <button
              aria-label={`Open agent ${turnDisplayName}`}
              className={cn(
                "flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-[10px] font-semibold transition-opacity hover:opacity-75",
                color?.bg,
                color?.fg
              )}
              onClick={() => onSelectAgent(turn.agentId)}
            >
              {agent ? deriveInitials(agent.role_name) : "??"}
            </button>
            <div className="flex flex-1 items-center justify-center self-stretch">
              <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                {turn.index + 1}
              </span>
            </div>
          </>
        ) : null}
      </div>
      <div className="min-w-0 flex-1 pr-4">
        {row.isTurnStart ? (
          <div className="mb-0.5 flex flex-wrap items-baseline gap-1.5">
            <button
              className="text-[13px] font-medium hover:underline"
              onClick={() => onSelectAgent(turn.agentId)}
            >
              {turnDisplayName}
            </button>
            <span className="text-[10px] text-muted-foreground">{formatTime(turn.timestamp)}</span>
          </div>
        ) : null}

        <div
          ref={el => {
            if (el) {
              messageRefs.current.set(entry.message_id, el);
            } else {
              messageRefs.current.delete(entry.message_id);
            }
          }}
          onMouseEnter={hasLinkedPair ? () => setHoveredCallId(entry.call_id) : undefined}
          onMouseLeave={hasLinkedPair ? () => setHoveredCallId(null) : undefined}
          onClick={hasLinkedPair ? () => jumpToMessage(entry.paired_message_id) : undefined}
          className={cn(
            "group/entry relative",
            entry.is_reasoning &&
              "ml-4 rounded-md border border-border/60 bg-muted/35 px-2 py-1.5 text-muted-foreground dark:bg-muted/20",
            !entry.is_reasoning &&
              !entry.is_tool_use &&
              !entry.is_notification_result &&
              !entry.is_run_cycle_failure &&
              "rounded-md border border-border/70 bg-background px-2 py-1.5 shadow-sm",
            (entry.is_tool_use || entry.is_notification_result || entry.is_run_cycle_failure) &&
              "ml-4",
            hasLinkedPair && "cursor-pointer",
            isLinkHovered && "rounded-md ring-2 ring-blue-400/40 dark:ring-blue-500/40",
            forkPointMessageId === entry.message_id &&
              "rounded-md bg-blue-50/60 px-2 py-1.5 ring-1 ring-blue-300/50 dark:bg-blue-950/30 dark:ring-blue-700/40"
          )}
        >
          {forkPointMessageId === entry.message_id ? (
            <span className="mb-0.5 inline-block rounded-full bg-blue-100 px-1.5 py-px text-[10px] font-medium leading-relaxed text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
              fork point (edited)
            </span>
          ) : null}

          {entry.is_reasoning ? (
            <span className="mb-1 inline-block rounded-full border border-border/70 bg-background/80 px-1.5 py-px text-[10px] font-medium text-muted-foreground">
              reasoning
            </span>
          ) : entry.is_tool_use ||
            entry.is_notification_result ||
            entry.is_run_cycle_failure ? null : showChannelBadge ? (
            <span
              className={cn(
                "mb-0.5 inline-block rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed",
                entryChColor?.bg,
                entryChColor?.fg
              )}
            >
              #{entry.channel_id}
            </span>
          ) : null}

          {entry.is_tool_use || entry.is_notification_result ? (
            <ToolOrNotification entry={entry} />
          ) : entry.is_run_cycle_failure ? (
            <RunCycleFailureDisplay
              errorType={entry.error_type}
              message={entry.text}
              cycle={entry.cycle}
            />
          ) : (
            <>
              {displayText ? (
                <ProseMarkdown
                  className={cn(
                    !entry.is_reasoning && "text-foreground",
                    "[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]"
                  )}
                >
                  {displayText.replace(/_/g, "\\_")}
                </ProseMarkdown>
              ) : null}
              {!entry.is_reasoning &&
              !entry.is_tool_use &&
              !entry.is_notification_result &&
              !entry.is_run_cycle_failure &&
              entry.character_count > 0 ? (
                <span className="mt-0.5 block text-[10px] text-muted-foreground/60">
                  {entry.character_count.toLocaleString()} characters
                </span>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
});
