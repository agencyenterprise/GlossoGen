"use client";

import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";

type VeyruStabilizeMetadata = components["schemas"]["VeyruStabilizeMetadata"];
type ContainerYardTruckMetadata = components["schemas"]["ContainerYardTruckMetadata"];
type ContainerYardCraneMetadata = components["schemas"]["ContainerYardCraneMetadata"];

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
  stabilizeMetadata?: VeyruStabilizeMetadata | null;
  truckMetadata?: ContainerYardTruckMetadata | null;
  craneMetadata?: ContainerYardCraneMetadata | null;
}

function ExpectedVsSubmittedRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-medium text-muted-foreground">{label}:</span>{" "}
      <span className="whitespace-pre-wrap">{value}</span>
    </div>
  );
}

function YardTruckMetadataBlock({ metadata }: { metadata: ContainerYardTruckMetadata }) {
  const expectedLines = metadata.expected_truck_assignments.map(a => {
    const cidSuffix = a.container_id !== "" ? ` (${a.container_id})` : "";
    return `${a.truck_role} → ${a.station_name}${cidSuffix}`;
  });
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Yard Verdict (step {metadata.step_index})
      </div>
      <div className="space-y-1 rounded bg-muted p-2 font-mono text-[10px]">
        <ExpectedVsSubmittedRow label="expected trucks" value={expectedLines.join("\n")} />
        <ExpectedVsSubmittedRow
          label="submitted"
          value={`${metadata.submitted_truck_role} → ${metadata.submitted_station_name}/${metadata.submitted_pad}${metadata.submitted_container_id !== "" ? ` (${metadata.submitted_container_id})` : ""}`}
        />
        <div>
          <span className="font-medium text-muted-foreground">accepted:</span>{" "}
          <span
            className={cn(
              "font-medium",
              metadata.overall_success ? "text-emerald-500" : "text-red-500"
            )}
          >
            {String(metadata.overall_success)}
          </span>
        </div>
        <div>
          <span className="font-medium text-muted-foreground">verdict:</span>{" "}
          <span>
            role={String(metadata.verdict.role_matches_active_assignment)}, station=
            {String(metadata.verdict.targets_correct_station)}, pad=
            {String(metadata.verdict.targets_correct_pad)}, container=
            {String(metadata.verdict.carries_correct_container)}
          </span>
        </div>
        {metadata.explanation !== "" ? (
          <ExpectedVsSubmittedRow label="explanation" value={metadata.explanation} />
        ) : null}
      </div>
    </div>
  );
}

function describeCraneMove(move: components["schemas"]["ContainerYardCraneMoveStep"]): string {
  const source =
    move.source_kind === "stack_tier"
      ? `stack ${move.source_stack}/tier ${move.source_tier}`
      : move.source_kind;
  const dest =
    move.destination_kind === "stack_tier"
      ? `stack ${move.destination_stack}/tier ${move.destination_tier}`
      : move.destination_kind;
  return `${move.container_id}: ${source} → ${dest}`;
}

function YardCraneMetadataBlock({ metadata }: { metadata: ContainerYardCraneMetadata }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Crane Verdict (step {metadata.step_index}, move {metadata.move_index})
      </div>
      <div className="space-y-1 rounded bg-muted p-2 font-mono text-[10px]">
        {metadata.expected_move !== null ? (
          <ExpectedVsSubmittedRow
            label="expected move"
            value={describeCraneMove(metadata.expected_move)}
          />
        ) : null}
        <ExpectedVsSubmittedRow
          label="submitted move"
          value={describeCraneMove(metadata.submitted_move)}
        />
        <div>
          <span className="font-medium text-muted-foreground">accepted:</span>{" "}
          <span
            className={cn("font-medium", metadata.accepted ? "text-emerald-500" : "text-red-500")}
          >
            {String(metadata.accepted)}
          </span>
        </div>
        <div>
          <span className="font-medium text-muted-foreground">verdict:</span>{" "}
          <span>
            matches_expected={String(metadata.verdict.matches_expected_next_move)}, source_holds=
            {String(metadata.verdict.source_currently_holds_container)}, dest_empty=
            {String(metadata.verdict.destination_currently_empty)}
          </span>
        </div>
        {metadata.explanation !== "" ? (
          <ExpectedVsSubmittedRow label="explanation" value={metadata.explanation} />
        ) : null}
      </div>
    </div>
  );
}

/** Renders a single tool call as a collapsible row. */
export function ToolCallDisplay({
  toolName,
  arguments: args,
  result,
  stabilizeMetadata,
  truckMetadata,
  craneMetadata,
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

          {stabilizeMetadata ? (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Judge Ground Truth
              </div>
              <div className="space-y-1 rounded bg-muted p-2 font-mono text-[10px]">
                <div>
                  <span className="font-medium text-muted-foreground">expected:</span>{" "}
                  <span className="whitespace-pre-wrap">{stabilizeMetadata.expected_actions}</span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">match:</span>{" "}
                  <span
                    className={cn(
                      "font-medium",
                      stabilizeMetadata.judge_match ? "text-emerald-500" : "text-red-500"
                    )}
                  >
                    {String(stabilizeMetadata.judge_match)}
                  </span>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">explanation:</span>{" "}
                  <span className="whitespace-pre-wrap">{stabilizeMetadata.judge_explanation}</span>
                </div>
              </div>
            </div>
          ) : null}

          {truckMetadata ? <YardTruckMetadataBlock metadata={truckMetadata} /> : null}
          {craneMetadata ? <YardCraneMetadataBlock metadata={craneMetadata} /> : null}
        </div>
      ) : null}
    </div>
  );
}
