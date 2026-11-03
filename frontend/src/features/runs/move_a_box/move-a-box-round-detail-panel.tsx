"use client";

import type { components } from "@/types/api.gen";
import { isScenarioExtras } from "../scenario-plugin";
import { FloorPlan } from "./floor-plan";
import { crateStyle, deltaLabel, IN_PLACE_ACTIONS, METHOD_MARKS, operatorColor } from "./marks";
import { roundFloors, roundMatchLabel, targetMatchLabel, targetStarts } from "./targets";
import { TemperatureTrace } from "./temperature-trace";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxTargetFloor = components["schemas"]["MoveABoxTargetFloor"];
type MoveABoxFloorBay = components["schemas"]["MoveABoxFloorBay"];

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

/** What the floor plan draws on bay ``number``: its number, or its symbol. */
function bayTag(number: number, bays: MoveABoxFloorBay[]): string {
  return bays.find(bay => bay.number === number)?.label ?? String(number);
}

function bayLabel(bay: number | null, bays: MoveABoxFloorBay[]): string {
  if (bay === null) return "no bay";
  return `bay ${bayTag(bay, bays)}`;
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

/** A result badge: green when the crates met, muted otherwise. */
function MatchBadge({ matched, label }: { matched: boolean; label: string }) {
  return (
    <span
      className={
        matched
          ? "rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800"
          : "rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
      }
    >
      {label}
    </span>
  );
}

/** The bays on every operator's list for one target, as the floor plans label them. */
function sharedBaysText(target: MoveABoxTargetFloor): string {
  return (
    target.shared_bays.map(bay => bayTag(bay, target.operators[0]?.bays ?? [])).join(", ") || "none"
  );
}

/** Every operator's floor for one target, side by side. */
function TargetFloors({ target, gridSize }: { target: MoveABoxTargetFloor; gridSize: number }) {
  return (
    <div className="flex flex-wrap gap-5">
      {target.operators.map((floor, index) => (
        <OperatorColumn
          key={floor.agent_id}
          floor={floor}
          index={index}
          operatorCount={target.operators.length}
          gridSize={gridSize}
          sharedBays={target.shared_bays}
        />
      ))}
    </div>
  );
}

/** One target of a round that holds several: its own heading, result and floors.
 *
 * Every target after the first starts each crate where the one before left it,
 * which is what the open circle on its floors marks. */
function TargetBlock({
  target,
  targetsPerRound,
  gridSize,
}: {
  target: MoveABoxTargetFloor;
  targetsPerRound: number;
  gridSize: number;
}) {
  return (
    <section
      className="mb-3 rounded-md border border-border/70 bg-background/60 p-2"
      aria-label={`Target ${target.target_number} of ${targetsPerRound}`}
    >
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[11px] font-semibold">
          Target {target.target_number} of {targetsPerRound}
        </span>
        <MatchBadge matched={target.scored && target.matched} label={targetMatchLabel(target)} />
        <span className="ml-auto text-[11px] text-muted-foreground">
          on every list: {sharedBaysText(target)}
        </span>
      </div>
      {target.target_number > 1 && (
        <div className="mb-1 text-[10px] text-muted-foreground">
          each crate starts where target {target.target_number - 1} left it
        </div>
      )}
      <TargetFloors target={target} gridSize={gridSize} />
    </section>
  );
}

interface OperatorColumnProps {
  floor: MoveABoxOperatorFloor;
  index: number;
  operatorCount: number;
  gridSize: number;
  sharedBays: number[];
}

function OperatorColumn({
  floor,
  index,
  operatorCount,
  gridSize,
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
        sharedBays={sharedBays}
        color={color}
      />
      <div className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
        <div>
          assigned {floor.allowed_bays.map(bay => bayTag(bay, floor.bays)).join(", ")} ·{" "}
          {floor.points} pts
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
              {crate.marking} · {bayLabel(crate.final_bay, floor.bays)} · {crate.final_temperature}C
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
      <span>a dot on a bay = on every operator&apos;s list</span>
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
 * the path its crate took, each step marked by the method that carried it. A
 * round of several targets shows one block per target, each with its own bays,
 * result and paths. The trace below puts every crate's readings for the whole
 * round on one scale, which is the only thing either operator could read of
 * the other, and marks where each later target began.
 */
export function MoveABoxRoundDetailPanel({ roundNumber, extras }: MoveABoxRoundDetailPanelProps) {
  if (!isScenarioExtras(extras, "move_a_box")) return null;
  const round = extras.cases.find(entry => entry.round_number === roundNumber) ?? null;
  if (round === null) return null;
  const first = round.targets[0];
  if (first === undefined) return null;
  const several = extras.targets_per_round > 1;
  const cratesEach = first.operators[0]?.crates.length ?? 1;

  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Round {round.round_number}
        </span>
        {several ? (
          <MatchBadge
            matched={round.matched}
            label={roundMatchLabel(round, extras.targets_per_round)}
          />
        ) : (
          <>
            <MatchBadge matched={first.scored && first.matched} label={targetMatchLabel(first)} />
            <span className="ml-auto text-[11px] text-muted-foreground">
              on every list: {sharedBaysText(first)}
            </span>
          </>
        )}
      </div>

      {several ? (
        round.targets.map(target => (
          <TargetBlock
            key={target.target_number}
            target={target}
            targetsPerRound={extras.targets_per_round}
            gridSize={round.grid_size}
          />
        ))
      ) : (
        <div className="mb-3">
          <TargetFloors target={first} gridSize={round.grid_size} />
        </div>
      )}

      <div className="mb-3">
        <MarkLegend deltas={extras.temperature_delta} cratesEach={cratesEach} />
      </div>

      <div className="mb-3">
        <TemperatureTrace
          floors={roundFloors(round)}
          baseTemperature={extras.base_temperature}
          targetStarts={several ? targetStarts(round) : []}
        />
      </div>
    </div>
  );
}
