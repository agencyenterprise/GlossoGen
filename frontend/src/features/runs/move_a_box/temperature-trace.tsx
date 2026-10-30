"use client";

import type { components } from "@/types/api.gen";
import { operatorColor, shortAgentName } from "./marks";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];

const WIDTH = 360;
const HEIGHT = 76;
const LEFT = 26;
const RIGHT = 44;
const TOP = 8;
const BOTTOM = 16;

interface Reading {
  sequence: number;
  value: number;
}

interface Series {
  agentId: string;
  color: string;
  dash: string | undefined;
  readings: Reading[];
}

/**
 * Every crate's readings against the round's own action sequence.
 *
 * A crate's reading holds between that operator's actions, so each line is drawn
 * as a staircase rather than interpolated: a flat stretch is a crate nobody
 * touched, not a crate drifting. Plotting them against the shared sequence is
 * what makes the lines comparable at a given moment, whether or not the run
 * held the operators in lockstep.
 */
function buildSeries(floors: MoveABoxOperatorFloor[], baseTemperature: number): Series[] {
  // One line per crate. Crates of one operator share its colour and are told
  // apart by their dash, the same way the floor plan draws their paths.
  return floors.flatMap((floor, index) =>
    floor.crates.map(crate => ({
      agentId: floor.crates.length > 1 ? crate.marking : floor.agent_id,
      color: operatorColor(index),
      dash: crate.slot === 1 ? undefined : DASHES[crate.slot % DASHES.length],
      readings: [
        { sequence: 0, value: baseTemperature },
        ...crate.steps.map(step => ({ sequence: step.sequence, value: step.temperature })),
      ],
    }))
  );
}

/** Dash patterns telling one operator's crates apart; slot 1 is solid. */
const DASHES = [undefined, undefined, "6 3", "2 3", "8 3 2 3"] as const;

interface TemperatureTraceProps {
  floors: MoveABoxOperatorFloor[];
  baseTemperature: number;
}

export function TemperatureTrace({ floors, baseTemperature }: TemperatureTraceProps) {
  const series = buildSeries(floors, baseTemperature);
  const everyReading = series.flatMap(line => line.readings.map(r => r.value));
  if (everyReading.length === 0) return null;
  const lastSequence = Math.max(1, ...series.flatMap(line => line.readings.map(r => r.sequence)));
  const low = Math.min(...everyReading);
  const high = Math.max(...everyReading);
  const span = high - low === 0 ? 1 : high - low;

  const xAt = (sequence: number) => LEFT + (sequence / lastSequence) * (WIDTH - LEFT - RIGHT);
  const yAt = (value: number) => TOP + (1 - (value - low) / span) * (HEIGHT - TOP - BOTTOM);

  return (
    <div>
      <div className="mb-1 flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          crate temperature, over the round&apos;s actions
        </span>
        <div className="flex items-center gap-2">
          {series.map(line => (
            <span key={line.agentId} className="flex items-center gap-1">
              <svg width={12} height={4} aria-hidden="true">
                <line
                  x1={0}
                  y1={2}
                  x2={12}
                  y2={2}
                  stroke={line.color}
                  strokeWidth={2}
                  strokeLinecap="round"
                />
              </svg>
              <span className="text-[10px] text-muted-foreground">{line.agentId}</span>
            </span>
          ))}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-[76px] w-full"
        role="img"
        aria-label="Both crates' temperature readings over the round's actions"
      >
        <line
          x1={LEFT}
          y1={yAt(high)}
          x2={WIDTH - RIGHT}
          y2={yAt(high)}
          className="stroke-border"
          strokeWidth={1}
        />
        <line
          x1={LEFT}
          y1={yAt(low)}
          x2={WIDTH - RIGHT}
          y2={yAt(low)}
          className="stroke-border"
          strokeWidth={1}
        />
        <text
          x={LEFT - 5}
          y={yAt(high) + 3}
          textAnchor="end"
          fontSize={9}
          className="fill-muted-foreground"
        >
          {high}
        </text>
        <text
          x={LEFT - 5}
          y={yAt(low) + 3}
          textAnchor="end"
          fontSize={9}
          className="fill-muted-foreground"
        >
          {low}
        </text>

        {series.map(line => {
          const points: string[] = [];
          let held = line.readings[0]!.value;
          for (const reading of line.readings) {
            points.push(`${xAt(reading.sequence)},${yAt(held)}`);
            points.push(`${xAt(reading.sequence)},${yAt(reading.value)}`);
            held = reading.value;
          }
          points.push(`${xAt(lastSequence)},${yAt(held)}`);
          return (
            <g key={line.agentId}>
              <polyline
                points={points.join(" ")}
                fill="none"
                stroke={line.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray={line.dash}
              />
              <circle cx={xAt(lastSequence)} cy={yAt(held)} r={4} fill={line.color} />
              <text
                x={xAt(lastSequence) + 8}
                y={yAt(held) + 3}
                fontSize={9}
                className="fill-muted-foreground"
              >
                {shortAgentName(line.agentId)} {held}
              </text>
            </g>
          );
        })}

        {Array.from({ length: lastSequence + 1 }, (_, sequence) => (
          <rect
            key={sequence}
            x={xAt(sequence) - (WIDTH - LEFT - RIGHT) / (lastSequence * 2)}
            y={0}
            width={Math.max((WIDTH - LEFT - RIGHT) / lastSequence, 4)}
            height={HEIGHT}
            fill="transparent"
          >
            <title>
              {`action ${sequence}\n` +
                series
                  .map(line => {
                    const upTo = line.readings.filter(r => r.sequence <= sequence);
                    const last = upTo[upTo.length - 1];
                    return `${line.agentId}: ${last === undefined ? "-" : last.value}`;
                  })
                  .join("\n")}
            </title>
          </rect>
        ))}
      </svg>
    </div>
  );
}
