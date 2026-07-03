"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { JudgeGroundTruthMetadata } from "./display-entry";

/** Strip the MCP prefix from tool names for display. */
function cleanToolName(name: string): string {
  return name.replace(/^mcp__comms__/, "");
}

/** Build a one-line parameter summary for the collapsed state. */
function paramSummary(args: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === "string" && value.length > 60) {
      parts.push(`${key}=${value.slice(0, 50)}...`);
    } else {
      parts.push(`${key}=${JSON.stringify(value)}`);
    }
  }
  const joined = parts.join(", ");
  if (joined.length > 100) {
    return joined.slice(0, 97) + "...";
  }
  return joined;
}

interface ToolCallDisplayProps {
  toolName: string;
  arguments: Record<string, unknown>;
  result: string | null;
  judgeMetadata?: JudgeGroundTruthMetadata | null;
  /** Scenario-specific supplementary content rendered by the scenario
   *  plug-in's ``renderToolMetadata`` hook (e.g. the container-yard move
   *  verdict). Null/undefined for tools and scenarios with nothing to add. */
  toolMetadata?: ReactNode;
}

/** Renders a single tool call as a collapsible row. */
export function ToolCallDisplay({
  toolName,
  arguments: args,
  result,
  judgeMetadata,
  toolMetadata,
}: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const displayName = cleanToolName(toolName);
  const summary = paramSummary(args);

  return (
    <div className="rounded border border-border/50 bg-muted/30 text-[11px]">
      <button
        className="flex w-full items-center gap-1.5 px-2 py-1 text-left hover:bg-muted/50"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight
          className={cn(
            "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-90"
          )}
        />
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="font-mono font-medium text-foreground">{displayName}</span>
        <span className="truncate text-muted-foreground">{summary}</span>
      </button>

      {expanded ? (
        <div className="space-y-2 border-t border-border/30 px-2 py-2">
          {/* Parameters */}
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Parameters
            </div>
            <div className="space-y-1">
              {Object.entries(args).map(([key, value]) => {
                const strValue = typeof value === "string" ? value : JSON.stringify(value, null, 2);
                const isLong = strValue.length > 200;
                return (
                  <div key={key}>
                    <span className="font-mono font-medium text-muted-foreground">{key}:</span>{" "}
                    {isLong ? (
                      <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 font-mono text-[10px]">
                        {strValue}
                      </pre>
                    ) : (
                      <span className="font-mono">{strValue}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Result */}
          {result ? (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Result
              </div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 font-mono text-[10px]">
                {result}
              </pre>
            </div>
          ) : null}

          {judgeMetadata ? (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Judge Ground Truth
              </div>
              <div className="space-y-1 rounded bg-muted p-2 font-mono text-[10px]">
                <div>
                  <span className="font-medium text-muted-foreground">expected:</span>{" "}
                  <span className="whitespace-pre-wrap">{judgeMetadata.expected_actions}</span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">match:</span>{" "}
                  <span
                    className={cn(
                      "font-medium",
                      judgeMetadata.judge_match ? "text-emerald-500" : "text-red-500"
                    )}
                  >
                    {String(judgeMetadata.judge_match)}
                  </span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">explanation:</span>{" "}
                  <span className="whitespace-pre-wrap">{judgeMetadata.judge_explanation}</span>
                </div>
              </div>
            </div>
          ) : null}

          {toolMetadata}
        </div>
      ) : null}
    </div>
  );
}
