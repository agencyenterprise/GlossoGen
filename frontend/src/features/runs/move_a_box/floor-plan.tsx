"use client";

import type { components } from "@/types/api.gen";
import { METHOD_MARKS } from "./marks";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxCell = components["schemas"]["MoveABoxCell"];

const CELL = 26;
const PAD = 10;

function cellKey(cell: MoveABoxCell): string {
  return `${cell.row}:${cell.col}`;
}

/** The centre of ``cell`` in the drawing's own coordinates. */
function centre(cell: MoveABoxCell): { x: number; y: number } {
  return { x: PAD + (cell.col - 0.5) * CELL, y: PAD + (cell.row - 0.5) * CELL };
}

/** Dash patterns telling one operator's crates apart; slot 1 is solid. */
const DASHES = [undefined, undefined, "6 3", "2 3", "8 3 2 3"] as const;

interface FloorPlanProps {
  floor: MoveABoxOperatorFloor;
  gridSize: number;
  bays: MoveABoxCell[];
  sharedBays: number[];
  color: string;
}

/**
 * One operator's floor: its pallets, the numbered bays, and each crate's path.
 * Crates of one operator share its colour and are told apart by their dash.
 *
 * A bay the depot did not assign this operator is drawn dashed and dimmed. The
 * bay assigned to every operator carries a dot, which is the ground truth no
 * operator was shown. Each step on the path wears the mark of the method that carried it, so
 * a run where the method never varies reads as one repeated mark.
 */
export function FloorPlan({ floor, gridSize, bays, sharedBays, color }: FloorPlanProps) {
  const width = gridSize * CELL + PAD * 2;
  const pallets = new Set(floor.pallets.map(cellKey));
  const allowed = new Set(floor.allowed_bays);
  const shared = new Set(sharedBays);
  const traces = floor.crates.map(crate => {
    const moves = crate.steps.filter(step => step.direction !== null);
    const points = [floor.start, ...moves.map(step => step.cell)].map(centre);
    return {
      crate,
      moves,
      points,
      line: points.map(point => `${point.x},${point.y}`).join(" "),
      endAt: centre(crate.final_cell),
    };
  });
  const startAt = centre(floor.start);
  const totalMoves = traces.reduce((sum, trace) => sum + trace.moves.length, 0);

  return (
    <svg
      width={width}
      height={width}
      viewBox={`0 0 ${width} ${width}`}
      role="img"
      aria-label={`Floor for ${floor.agent_id}, ${floor.crates.length} crates, ${totalMoves} moves`}
      className="shrink-0"
    >
      {Array.from({ length: gridSize }, (_, row) =>
        Array.from({ length: gridSize }, (_, col) => {
          const key = `${row + 1}:${col + 1}`;
          const isPallet = pallets.has(key);
          return (
            <rect
              key={key}
              x={PAD + col * CELL}
              y={PAD + row * CELL}
              width={CELL}
              height={CELL}
              className={
                isPallet
                  ? "fill-muted-foreground/25 stroke-border"
                  : "fill-transparent stroke-border"
              }
              strokeWidth={1}
            />
          );
        })
      )}

      {bays.map((bay, index) => {
        const number = index + 1;
        const open = allowed.has(number);
        const isFinal = floor.crates.some(crate => crate.final_bay === number);
        const at = centre(bay);
        return (
          <g key={number} opacity={open ? 1 : 0.4}>
            <rect
              x={at.x - CELL / 2 + 2}
              y={at.y - CELL / 2 + 2}
              width={CELL - 4}
              height={CELL - 4}
              rx={4}
              fill={isFinal ? color : "transparent"}
              fillOpacity={isFinal ? 0.9 : 0}
              className={open ? "stroke-foreground/60" : "stroke-foreground/40"}
              strokeWidth={open ? 1.5 : 1}
              strokeDasharray={open ? undefined : "3 2"}
            />
            {shared.has(number) && (
              <circle cx={at.x} cy={at.y - CELL / 2 + 1} r={2.5} className="fill-foreground/70" />
            )}
            <text
              x={at.x}
              y={at.y + 3.5}
              textAnchor="middle"
              className={isFinal ? "fill-background" : "fill-foreground"}
              fontSize={10}
              fontWeight={600}
            >
              {number}
            </text>
            <title>
              {`Bay ${number}${open ? "" : " (not assigned to this operator)"}${
                shared.has(number) ? " · on every operator's list" : ""
              }`}
            </title>
          </g>
        );
      })}

      <circle cx={startAt.x} cy={startAt.y} r={4} fill="none" stroke={color} strokeWidth={2} />

      {traces.map(({ crate, moves, points, line, endAt }) => (
        <g key={crate.crate_id}>
          {points.length > 1 && (
            <polyline
              points={line}
              fill="none"
              stroke={color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={crate.slot === 1 ? undefined : DASHES[crate.slot % DASHES.length]}
              opacity={0.75}
            />
          )}
          {moves.map((step, index) => {
            const at = points[index + 1]!;
            const mark = METHOD_MARKS[step.action];
            if (mark === undefined) return null;
            return (
              <g key={step.sequence}>
                {mark.shape === "square" ? (
                  <rect
                    x={at.x - 3.5}
                    y={at.y - 3.5}
                    width={7}
                    height={7}
                    fill={mark.filled ? color : "var(--background, #fff)"}
                    stroke={color}
                    strokeWidth={1.5}
                  />
                ) : (
                  <circle
                    cx={at.x}
                    cy={at.y}
                    r={4}
                    fill={mark.filled ? color : "var(--background, #fff)"}
                    stroke={color}
                    strokeWidth={1.5}
                  />
                )}
                <title>{`${crate.marking} #${step.sequence} ${step.action} ${step.direction ?? ""} → ${step.temperature}C`}</title>
              </g>
            );
          })}
          {crate.finished && (
            <circle
              cx={endAt.x}
              cy={endAt.y}
              r={8}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeDasharray="2 2"
            />
          )}
        </g>
      ))}
    </svg>
  );
}
