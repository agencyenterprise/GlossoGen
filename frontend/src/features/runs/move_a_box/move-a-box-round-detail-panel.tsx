"use client";

import type { components } from "@/types/api.gen";
import { FloorPlan } from "./floor-plan";
import { crateStyle, deltaLabel, IN_PLACE_ACTIONS, METHOD_MARKS, operatorColor } from "./marks";
import { TemperatureTrace } from "./temperature-trace";

type MoveABoxRunExtras = components["schemas"]["MoveABoxRunExtras"];
type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxRoundFloor = components["schemas"]["MoveABoxRoundFloor"];

function isMoveABoxExtras(extras: unknown): extras is MoveABoxRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "move_a_box";
}

/** How many of each action the operator took, in the order the legend lists them. */
function actionTally(floor: MoveABoxOperatorFloor): string {
  const counts = new Map<string, number>();
  for (const step of floor.crates.flatMap(crate => crate.steps)) {
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

/** The badge and line style the floor plan drew for one crate, so the panel's
 *  per-crate rows map onto the paths without the reader guessing. */
function CrateKey({
  slot,
  operatorIndex,
  cratesEach,
  operatorCount,
}: {
  slot: number;
  operatorIndex: number;
  cratesEach: number;
  operatorCount: number;
}) {
  const style = crateStyle({ slot, operatorIndex, cratesEach, operatorCount });
  const showBadge = cratesEach > 1;
  const color = style.color;
  return (
    <svg width={showBadge ? 34 : 22} height={13} aria-hidden="true" className="shrink-0">
      {showBadge && (
        <>
          <circle cx={6.5} cy={6.5} r={6} fill={color} />
          <text
            x={6.5}
            y={9.5}
            textAnchor="middle"
            className="fill-background"
            fontSize={8}
            fontWeight={700}
          >
            {slot}
          </text>
        </>
      )}
      <line
        x1={showBadge ? 15 : 1}
        y1={6.5}
        x2={showBadge ? 33 : 21}
        y2={6.5}
        stroke={color}
        strokeWidth={2}
        strokeDasharray={style.dash}
      />
    </svg>
  );
}

/** What the round's badge says about the crates meeting.
 *
 * One crate a side has one thing to say. More than one, and the badge names
 * the slots that met, since which ones they were is the whole result. */
function matchLabel(round: MoveABoxRoundFloor): string {
  const perOperator = round.operators[0]?.crates.length ?? 1;
  if (perOperator <= 1) return round.matched ? "same bay" : "different bays";
  if (round.matched) return `all ${perOperator} crates met`;
  if (round.matched_slots.length === 0) return `no crate met (0 of ${perOperator})`;
  return `crate ${round.matched_slots.join(" and ")} met, ${
    perOperator - round.matched_slots.length
  } did not`;
}

interface OperatorColumnProps {
  floor: MoveABoxOperatorFloor;
  index: number;
  operatorCount: number;
  gridSize: number;
  bays: components["schemas"]["MoveABoxCell"][];
  sharedBays: number[];
}

function OperatorColumn({
  floor,
  index,
  operatorCount,
  gridSize,
  bays,
  sharedBays,
}: OperatorColumnProps) {
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
        {floor.crates.length > 1 && (
          <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
            {floor.crates.length} crates
          </span>
        )}
      </div>
      <FloorPlan
        floor={floor}
        operatorIndex={index}
        operatorCount={operatorCount}
        gridSize={gridSize}
        bays={bays}
        sharedBays={sharedBays}
        color={color}
      />
      <div className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
        <div>
          assigned {floor.allowed_bays.join(", ")} · {floor.points} pts
        </div>
        {floor.crates.map(crate => (
          <div key={crate.crate_id} className="flex items-center gap-1.5 font-mono">
            <CrateKey
              slot={crate.slot}
              operatorIndex={index}
              cratesEach={floor.crates.length}
              operatorCount={operatorCount}
            />
            <span className="truncate">
              {crate.marking} · {bayLabel(crate.final_bay)} · {crate.final_temperature}C
            </span>
          </div>
        ))}
        <div className="font-mono">{actionTally(floor)}</div>
      </div>
    </div>
  );
}

/** The shape a haul method is drawn with, in words, for a tooltip. */
function markShapeName(mark: { shape: string; filled: boolean }): string {
  const body = mark.filled ? "filled" : "empty";
  return `${body} ${mark.shape}`;
}

interface MarkLegendProps {
  deltas: Record<string, number>;
  cratesEach: number;
}

/** What the floor plan's marks and colours mean.
 *
 * The shapes say how a step was carried, which is the one thing the readings
 * answer to. With several crates a side, the colours say which crate, so that
 * is spelled out here rather than left to the per-operator rows. */
function MarkLegend({ deltas, cratesEach }: MarkLegendProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
      <span className="font-medium text-foreground">how a step was carried:</span>
      {Object.entries(METHOD_MARKS).map(([method, mark]) => (
        <span
          key={method}
          className="flex items-center gap-1"
          title={`${markShapeName(mark)} = ${deltaLabel(method, deltas)}`}
        >
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
        <span key={action} title={`${action.replace("_", " ")} leaves the crate where it stands`}>
          {deltaLabel(action, deltas)}
        </span>
      ))}
      <span>&#9679; on a bay = on every operator&apos;s list</span>
      {cratesEach > 1 && (
        <>
          {/* A full-basis item wraps the flex row, so the crate key starts its own line. */}
          <span className="basis-full" aria-hidden="true" />
          <span className="font-medium text-foreground">which crate (each in its own colour):</span>
          {Array.from({ length: cratesEach }, (_, index) => index + 1).map(slot => (
            <span
              key={slot}
              className="flex items-center gap-1"
              title={`Crate ${slot} of each operator: this line and this badge, in that operator\u2019s own colour for that crate.`}
            >
              <svg width={30} height={11} aria-hidden="true">
                <circle cx={5.5} cy={5.5} r={5} className="fill-foreground" />
                <text
                  x={5.5}
                  y={8.5}
                  textAnchor="middle"
                  className="fill-background"
                  fontSize={7}
                  fontWeight={700}
                >
                  {slot}
                </text>
                <line
                  x1={13}
                  y1={5.5}
                  x2={30}
                  y2={5.5}
                  className="stroke-foreground"
                  strokeWidth={2}
                  strokeDasharray={
                    crateStyle({ slot, operatorIndex: 0, cratesEach, operatorCount: 1 }).dash
                  }
                />
              </svg>
              crate {slot}
            </span>
          ))}
        </>
      )}
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
  const cratesEach = round.operators[0]?.crates.length ?? 1;

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
          {matchLabel(round)}
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
            operatorCount={round.operators.length}
            gridSize={round.grid_size}
            bays={round.bays}
            sharedBays={round.shared_bays}
          />
        ))}
      </div>

      <div className="mb-3">
        <MarkLegend deltas={extras.temperature_delta} cratesEach={cratesEach} />
      </div>

      <div className="mb-3">
        <TemperatureTrace floors={round.operators} baseTemperature={extras.base_temperature} />
      </div>
    </div>
  );
}
