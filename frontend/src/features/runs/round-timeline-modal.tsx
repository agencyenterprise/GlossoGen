"use client";

import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { Check, Hash, X } from "lucide-react";
import type { components } from "@/types/api.gen";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { getScenarioPlugin } from "./scenario-registry";

type RunDetailResponse = components["schemas"]["RunDetailResponse"];
type ScenarioExtras = NonNullable<RunDetailResponse["scenario_extras"]>;
type RoundEnding = components["schemas"]["RoundEnding"];
type ContainerYardMoveMetadata = components["schemas"]["ContainerYardMoveMetadata"];

interface RoundTimelineModalProps {
  roundNumber: number;
  messages: DisplayEntry[];
  scenarioName: string;
  scenarioExtras: ScenarioExtras | null;
  roundEnding: RoundEnding | null;
  onClose: () => void;
}

interface TimelineRow {
  key: string;
  timestamp: string;
  kind: "message" | "judged_tool";
  sender: string;
  text: string;
  toolName: string;
  verdictAccepted: boolean | null;
  expected: string;
  explanation: string;
}

function formatMoveArgs(args: Record<string, unknown>): string {
  const from = typeof args.from_slot === "number" ? args.from_slot : "?";
  const to = typeof args.to_slot === "number" ? args.to_slot : "?";
  return `slot ${from} → slot ${to}`;
}

function formatExpectedMove(metadata: ContainerYardMoveMetadata): string {
  const from = metadata.expected_from_slot === null ? "?" : String(metadata.expected_from_slot);
  const to = metadata.expected_to_slot === null ? "?" : String(metadata.expected_to_slot);
  return `slot ${from} → slot ${to}`;
}

function moveVerdictAccepted(metadata: ContainerYardMoveMetadata): boolean | null {
  if (metadata.accepted) return true;
  if (metadata.soft_rejected) return null;
  return false;
}

function buildTimelineRows(messages: DisplayEntry[], primaryChannelId: string): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (const m of messages) {
    if (m.is_reasoning || m.is_run_cycle_failure || m.is_notification_result) continue;
    if (m.is_tool_use && m.judge_metadata !== null) {
      const action =
        typeof m.tool_arguments.action === "string"
          ? (m.tool_arguments.action as string)
          : JSON.stringify(m.tool_arguments);
      rows.push({
        key: m.message_id,
        timestamp: m.timestamp,
        kind: "judged_tool",
        sender: m.sender_agent_id,
        text: action,
        toolName: m.tool_name,
        verdictAccepted: m.judge_metadata.judge_match,
        expected: m.judge_metadata.expected_actions,
        explanation: m.judge_metadata.judge_explanation,
      });
      continue;
    }
    if (m.is_tool_use && m.move_metadata !== null) {
      rows.push({
        key: m.message_id,
        timestamp: m.timestamp,
        kind: "judged_tool",
        sender: m.sender_agent_id,
        text: formatMoveArgs(m.tool_arguments),
        toolName: "move_container",
        verdictAccepted: moveVerdictAccepted(m.move_metadata),
        expected: formatExpectedMove(m.move_metadata),
        explanation: m.move_metadata.explanation,
      });
      continue;
    }
    if (m.is_tool_use) continue;
    if (m.channel_id !== primaryChannelId) continue;
    rows.push({
      key: m.message_id,
      timestamp: m.timestamp,
      kind: "message",
      sender: m.sender_agent_id,
      text: m.text,
      toolName: "",
      verdictAccepted: null,
      expected: "",
      explanation: "",
    });
  }
  return rows;
}

function TriggerBadge({ trigger }: { trigger: string }) {
  let tone: string;
  if (trigger === "veyru_stabilized" || trigger === "round_completed") {
    tone = "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400";
  } else if (trigger === "veyru_collapsed" || trigger === "round_failed") {
    tone = "bg-rose-500/15 text-rose-600 dark:text-rose-400";
  } else {
    tone = "bg-amber-500/15 text-amber-600 dark:text-amber-400";
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {humanize(trigger)}
    </span>
  );
}

function VerdictPill({ accepted }: { accepted: boolean }) {
  if (accepted) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
        <Check className="h-3 w-3" />
        accepted
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium text-rose-700 dark:text-rose-400">
      <X className="h-3 w-3" />
      rejected
    </span>
  );
}

export function RoundTimelineModal({
  roundNumber,
  messages,
  scenarioName,
  scenarioExtras,
  roundEnding,
  onClose,
}: RoundTimelineModalProps) {
  const plugin = getScenarioPlugin(scenarioName);
  const RoundDetailPanel = plugin.RoundDetailPanel;
  const primaryChannelId = plugin.primaryChannelId;
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const rows = useMemo(
    () => buildTimelineRows(messages, primaryChannelId),
    [messages, primaryChannelId]
  );

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="mx-4 flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Round {roundNumber} timeline</span>
            {roundEnding !== null ? <TriggerBadge trigger={roundEnding.trigger} /> : null}
          </div>
          <button
            aria-label="Close"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {RoundDetailPanel !== null ? (
            <RoundDetailPanel roundNumber={roundNumber} extras={scenarioExtras} />
          ) : null}

          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Timeline
          </div>
          {rows.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              No link messages or judged tool calls recorded for this round.
            </div>
          ) : (
            <ol className="relative space-y-3 border-l border-border pl-4">
              {rows.map(row => {
                let dotClass: string;
                if (row.kind === "judged_tool" && row.verdictAccepted === true) {
                  dotClass = "bg-emerald-500";
                } else if (row.kind === "judged_tool" && row.verdictAccepted === false) {
                  dotClass = "bg-rose-500";
                } else {
                  dotClass = "bg-muted-foreground";
                }
                return (
                  <li key={row.key} className="relative">
                    <span
                      className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background ${dotClass}`}
                    />
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="font-mono">{formatTime(row.timestamp)}</span>
                      <span className="font-medium text-foreground">{humanize(row.sender)}</span>
                      {row.kind === "judged_tool" ? (
                        <>
                          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                            {row.toolName}
                          </span>
                          {row.verdictAccepted !== null ? (
                            <VerdictPill accepted={row.verdictAccepted} />
                          ) : null}
                        </>
                      ) : (
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                          #{primaryChannelId}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 whitespace-pre-wrap break-words text-[13px] leading-relaxed">
                      {row.text}
                    </div>
                    {row.kind === "judged_tool" &&
                    (row.expected !== "" || row.explanation !== "") ? (
                      <div className="mt-1.5 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 text-[11px] text-muted-foreground">
                        {row.expected !== "" ? (
                          <div>
                            <span className="text-[10px] uppercase tracking-wide">expected</span>{" "}
                            {row.expected}
                          </div>
                        ) : null}
                        {row.explanation !== "" ? (
                          <div className="mt-1">
                            <span className="text-[10px] uppercase tracking-wide">verdict</span>{" "}
                            {row.explanation}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
