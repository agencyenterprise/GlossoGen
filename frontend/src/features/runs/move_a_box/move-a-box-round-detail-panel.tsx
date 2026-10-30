"use client";

import type { components } from "@/types/api.gen";
import { FloorPlan } from "./floor-plan";
import { deltaLabel, IN_PLACE_ACTIONS, METHOD_MARKS, operatorColor } from "./marks";
import { TemperatureTrace } from "./temperature-trace";

type MoveABoxRunExtras = components["schemas"]["MoveABoxRunExtras"];
type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];

function isMoveABoxExtras(extras: unknown): extras is MoveABoxRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "move_a_box";
}

/** How many of each action the operator took, in the order the legend lists them. */
function actionTally(floor: MoveABoxOperatorFloor): string {
  const counts = new Map<string, number>();
  for (const step of floor.steps) {
    counts.set(step.action, (counts.get(step.action) ?? 0) + 1);
  }
  const parts = [...counts.entries()].map(([action, count]) => `${count}x ${action}`);
  if (parts.length === 0) return "no actions";
  return parts.join(" · ");
}

function bayLabel(bay: number | null): string {
  if (bay === null) return "no bay";
  return `bay ${bay}`;
}

interface OperatorColumnProps {
  floor: MoveABoxOperatorFloor;
  index: number;
  gridSize: number;
  bays: components["schemas"]["MoveABoxCell"][];
  sharedBays: number[];
}

function OperatorColumn({ floor, index, gridSize, bays, sharedBays }: OperatorColumnProps) {
  const color = operatorColor(index);
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline gap-2">
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        <span className="truncate text-xs font-medium">{floor.agent_id}</span>
        <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
          {floor.crate_id}
        </span>
      </div>
      <FloorPlan
        floor={floor}
        gridSize={gridSize}
        bays={bays}
        sharedBays={sharedBays}
        color={color}
      />
      <div className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
        <div>
          assigned {floor.allowed_bays.join(", ")} · left on {bayLabel(floor.final_bay)} ·{" "}
          {floor.points} pts
        </div>
        <div className="font-mono">{actionTally(floor)}</div>
      </div>
    </div>
  );
}

interface MarkLegendProps {
  deltas: Record<string, number>;
}

/** The marks the floor plan draws, so a reader knows what each one means. */
function MarkLegend({ deltas }: MarkLegendProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
      {Object.entries(METHOD_MARKS).map(([method, mark]) => (
        <span key={method} className="flex items-center gap-1">
          <svg width={10} height={10} aria-hidden="true">
            {mark.shape === "square" ? (
              <rect
                x={1.5}
                y={1.5}
                width={7}
                height={7}
                className="stroke-foreground"
                fill={mark.filled ? "currentColor" : "none"}
                strokeWidth={1.5}
              />
            ) : (
              <circle
                cx={5}
                cy={5}
                r={3.5}
                className="stroke-foreground"
                fill={mark.filled ? "currentColor" : "none"}
                strokeWidth={1.5}
              />
            )}
          </svg>
          {deltaLabel(method, deltas)}
        </span>
      ))}
      {IN_PLACE_ACTIONS.map(action => (
        <span key={action}>{deltaLabel(action, deltas)}</span>
      ))}
      <span>● on a bay = assigned to both</span>
    </div>
  );
}

interface MoveABoxRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/**
 * move_a_box floor plans for one round, rendered above the round timeline.
 *
 * Each operator's floor shows its own pallets, which bays they leave open, and
 * the path its crate took, each step marked by the method that carried it. The
 * trace below puts both crates' readings on one scale, which is the only thing
 * either operator could read of the other.
 */
export function MoveABoxRoundDetailPanel({ roundNumber, extras }: MoveABoxRoundDetailPanelProps) {
  if (!isMoveABoxExtras(extras)) return null;
  const round = extras.cases.find(entry => entry.round_number === roundNumber) ?? null;
  if (round === null) return null;
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Round {round.round_number}
        </span>
        <span
          className={
            round.matched
              ? "rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800"
              : "rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
          }
        >
          {round.matched ? "same bay" : "different bays"}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          on every list: {round.shared_bays.join(", ") || "none"}
        </span>
      </div>

      <div className="mb-3 flex flex-wrap gap-5">
        {round.operators.map((floor, index) => (
          <OperatorColumn
            key={floor.agent_id}
            floor={floor}
            index={index}
            gridSize={round.grid_size}
            bays={round.bays}
            sharedBays={round.shared_bays}
          />
        ))}
      </div>

      <div className="mb-3">
        <TemperatureTrace floors={round.operators} baseTemperature={extras.base_temperature} />
      </div>

      <MarkLegend deltas={extras.temperature_delta} />
    </div>
  );
}
