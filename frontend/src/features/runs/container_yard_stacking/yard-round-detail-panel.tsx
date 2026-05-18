"use client";

import type { components } from "@/types/api.gen";

type ContainerYardRunExtras = components["schemas"]["ContainerYardRunExtras"];
type ContainerYardCraneMoveStep = components["schemas"]["ContainerYardCraneMoveStep"];
type ContainerYardTruckAssignment = components["schemas"]["ContainerYardTruckAssignment"];
type ContainerYardStackSnapshot = components["schemas"]["ContainerYardStackSnapshot"];

function isYardExtras(extras: unknown): extras is ContainerYardRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "container_yard_stacking";
}

function describeCraneMove(move: ContainerYardCraneMoveStep): string {
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

function describeTruck(assignment: ContainerYardTruckAssignment): string {
  const cidSuffix = assignment.container_id !== "" ? ` (${assignment.container_id})` : "";
  return `${assignment.truck_role} → ${assignment.station_name}${cidSuffix}`;
}

function describeStack(snapshot: ContainerYardStackSnapshot): string {
  if (snapshot.containers_bottom_to_top.length === 0) return "empty";
  return snapshot.containers_bottom_to_top.map((cid, idx) => `T${idx + 1}=${cid}`).join(", ");
}

interface YardRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/** Container-yard case-detail header rendered at the top of the round-timeline modal. */
export function YardRoundDetailPanel({ roundNumber, extras }: YardRoundDetailPanelProps) {
  if (!isYardExtras(extras)) return null;
  const yardCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (yardCase === null) return null;
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-1 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Case {yardCase.case_number}
        </span>
        <span className="text-sm font-medium">
          {yardCase.steps.length} delivery{yardCase.steps.length === 1 ? "" : "ies"}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          budget {yardCase.round_time_budget_seconds}s
        </span>
      </div>

      <div className="mb-3 space-y-1 text-[11px] text-muted-foreground">
        <div>
          <span className="text-[10px] uppercase tracking-wide">stations</span>{" "}
          {yardCase.active_crane_stations.map(s => (
            <span key={s.station_name} className="mr-2 font-mono">
              {s.station_name} (pads: {s.pads.join("/")}, reaches: {s.reachable_stacks.join(",")})
            </span>
          ))}
        </div>
        <div>
          <span className="text-[10px] uppercase tracking-wide">layout</span>{" "}
          {yardCase.initial_stacks.map(stack => (
            <span key={stack.stack} className="mr-2 font-mono">
              stack {stack.stack}: {describeStack(stack)};
            </span>
          ))}
        </div>
        <div>
          <span className="text-[10px] uppercase tracking-wide">manifest</span>{" "}
          {yardCase.manifest.map(entry => (
            <span key={entry.container_id} className="mr-2 font-mono">
              {entry.container_id} → S{entry.target_position.stack}/T{entry.target_position.tier};
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {yardCase.steps.map(step => (
          <div
            key={step.step_index}
            className="rounded-md border border-border/70 bg-background px-3 py-2 text-xs"
          >
            <div className="mb-1 flex items-center gap-2">
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                step {step.step_index}
              </span>
              <span className="font-medium">{step.incoming_container_id}</span>
              <span className="text-muted-foreground">
                → stack {step.target_position.stack}, tier {step.target_position.tier}
              </span>
              <span className="text-muted-foreground">·</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {step.correct_crane_station}
              </span>
            </div>
            <div className="mb-1 text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">trucks</span>{" "}
              {step.truck_assignments.map(describeTruck).join("; ")}
            </div>
            <div className="text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">crane plan</span>{" "}
              {step.expected_move_sequence.map(describeCraneMove).join(" → ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
