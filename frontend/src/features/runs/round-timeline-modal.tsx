"use client";

import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { Check, Hash, X } from "lucide-react";
import type { components } from "@/types/api.gen";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";

type VeyruCaseSummary = components["schemas"]["VeyruCaseSummary"];
type RoundEnding = components["schemas"]["RoundEnding"];

interface RoundTimelineModalProps {
  roundNumber: number;
  messages: DisplayEntry[];
  veyruCase: VeyruCaseSummary | null;
  roundEnding: RoundEnding | null;
  onClose: () => void;
}

interface TimelineRow {
  key: string;
  timestamp: string;
  kind: "message" | "stabilize" | "end";
  sender: string;
  text: string;
  judgeMatch: boolean | null;
  judgeExpected: string;
  judgeExplanation: string;
}

function buildTimelineRows(messages: DisplayEntry[]): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (const m of messages) {
    if (m.is_reasoning || m.is_run_cycle_failure || m.is_notification_result) continue;
    if (m.is_tool_use && m.tool_name === "stabilize_veyru") {
      const action =
        typeof m.tool_arguments.action === "string"
          ? (m.tool_arguments.action as string)
          : JSON.stringify(m.tool_arguments);
      rows.push({
        key: m.message_id,
        timestamp: m.timestamp,
        kind: "stabilize",
        sender: m.sender_agent_id,
        text: action,
        judgeMatch: m.stabilize_metadata?.judge_match ?? null,
        judgeExpected: m.stabilize_metadata?.expected_actions ?? "",
        judgeExplanation: m.stabilize_metadata?.judge_explanation ?? "",
      });
      continue;
    }
    if (m.is_tool_use) continue;
    if (m.channel_id !== "link") continue;
    rows.push({
      key: m.message_id,
      timestamp: m.timestamp,
      kind: "message",
      sender: m.sender_agent_id,
      text: m.text,
      judgeMatch: null,
      judgeExpected: "",
      judgeExplanation: "",
    });
  }
  return rows;
}

function TriggerBadge({ trigger }: { trigger: string }) {
  const tone =
    trigger === "veyru_stabilized"
      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
      : trigger === "veyru_collapsed"
        ? "bg-rose-500/15 text-rose-600 dark:text-rose-400"
        : "bg-amber-500/15 text-amber-600 dark:text-amber-400";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {humanize(trigger)}
    </span>
  );
}

function JudgePill({ match }: { match: boolean }) {
  if (match) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
        <Check className="h-3 w-3" />
        judge match
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium text-rose-700 dark:text-rose-400">
      <X className="h-3 w-3" />
      judge mismatch
    </span>
  );
}

export function RoundTimelineModal({
  roundNumber,
  messages,
  veyruCase,
  roundEnding,
  onClose,
}: RoundTimelineModalProps) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const rows = useMemo(() => buildTimelineRows(messages), [messages]);

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
          {veyruCase !== null ? (
            <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Case {veyruCase.case_number}
                </span>
                <span className="text-sm font-medium">{veyruCase.failure_name}</span>
                <span className="ml-auto text-[11px] text-muted-foreground">
                  budget {veyruCase.time_budget_seconds}s
                </span>
              </div>
              <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                <span>
                  stellar offset{" "}
                  <span className="font-mono">{veyruCase.stellar_reading.offset}</span>
                </span>
                <span>
                  face <span className="font-mono">{veyruCase.stellar_reading.starting_face}</span>
                </span>
                <span>
                  hold <span className="font-mono">{veyruCase.stellar_reading.hold_duration}s</span>
                </span>
                <span>
                  intensity{" "}
                  <span className="font-mono">{veyruCase.stellar_reading.intensity_level}</span>
                </span>
              </div>
              <div className="space-y-2">
                {veyruCase.stages.map((stage, idx) => (
                  <div
                    key={`${stage.motif_name}-${idx}`}
                    className="rounded-md border border-border/70 bg-background px-3 py-2 text-xs"
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        stage {idx}
                      </span>
                      <span className="font-medium">{stage.motif_name}</span>
                      <span className="text-muted-foreground">→</span>
                      <span className="text-muted-foreground">{stage.treatment_motif_name}</span>
                    </div>
                    <div className="mb-1 text-muted-foreground">
                      <span className="text-[10px] uppercase tracking-wide">symptoms</span>{" "}
                      {stage.observable_symptoms}
                    </div>
                    <div className="text-muted-foreground">
                      <span className="text-[10px] uppercase tracking-wide">expected</span>{" "}
                      {stage.judge_expected_actions}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Timeline
          </div>
          {rows.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              No link messages or stabilize calls recorded for this round.
            </div>
          ) : (
            <ol className="relative space-y-3 border-l border-border pl-4">
              {rows.map(row => (
                <li key={row.key} className="relative">
                  <span
                    className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background ${
                      row.kind === "stabilize"
                        ? row.judgeMatch === true
                          ? "bg-emerald-500"
                          : "bg-rose-500"
                        : "bg-muted-foreground"
                    }`}
                  />
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="font-mono">{formatTime(row.timestamp)}</span>
                    <span className="font-medium text-foreground">{humanize(row.sender)}</span>
                    {row.kind === "stabilize" ? (
                      <>
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                          stabilize_veyru
                        </span>
                        {row.judgeMatch !== null ? <JudgePill match={row.judgeMatch} /> : null}
                      </>
                    ) : (
                      <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                        #link
                      </span>
                    )}
                  </div>
                  <div className="mt-1 whitespace-pre-wrap break-words text-[13px] leading-relaxed">
                    {row.text}
                  </div>
                  {row.kind === "stabilize" && row.judgeExpected !== "" ? (
                    <div className="mt-1.5 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 text-[11px] text-muted-foreground">
                      <div>
                        <span className="text-[10px] uppercase tracking-wide">expected</span>{" "}
                        {row.judgeExpected}
                      </div>
                      {row.judgeExplanation !== "" ? (
                        <div className="mt-1">
                          <span className="text-[10px] uppercase tracking-wide">judge</span>{" "}
                          {row.judgeExplanation}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
