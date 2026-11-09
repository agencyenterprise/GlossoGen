/**
 * The SVG marks of the move_a_box clock lanes.
 *
 * Each operator's round is one ribbon of spans in time order: its own colour
 * while it thinks, a light tint of it while an action is under way, and a
 * neutral grey while it waits. Spans are kept apart by a 2px gap in the surface
 * colour rather than an outline. A pin marks a finish, and an arrow in the
 * acting operator's colour marks each wait that operator's landing ended.
 */

import type { ReactNode } from "react";
import type { components } from "@/types/api.gen";
import { directionGlyph, finishBay, seconds } from "./clock-lanes-labels";
import { operatorColor } from "./marks";

type MoveABoxClockLane = components["schemas"]["MoveABoxClockLane"];

export const LANE_HEIGHT = 46;
export const TRACK_HEIGHT = 16;
/** Room above each ribbon for the finish pins. */
const TRACK_TOP = 18;
const AXIS_HEIGHT = 22;
export const PLOT_LEFT = 2;
const PLOT_RIGHT = 10;
/** The tint an action under way wears over its operator's colour. */
export const ACTING_OPACITY = 0.38;
/** The grey a wait wears, as an opacity of the text colour. */
export const WAITING_OPACITY = 0.09;
/** Two times closer than this are one instant. */
const SAME_INSTANT_S = 1e-6;
/** The width of the crosshair's time chip on the axis. */
const CHIP_WIDTH = 46;

/** Where things go: the x of a second, and the rows the lanes and axis take. */
export interface ClockGeometry {
  xAt: (seconds: number) => number;
  pxPerSecond: number;
  width: number;
  lanesBottom: number;
  height: number;
}

export function clockGeometry(duration: number, laneCount: number, width: number): ClockGeometry {
  const pxPerSecond = (width - PLOT_LEFT - PLOT_RIGHT) / Math.max(duration, 1);
  const lanesBottom = laneCount * LANE_HEIGHT;
  return {
    xAt: value => PLOT_LEFT + value * pxPerSecond,
    pxPerSecond,
    width,
    lanesBottom,
    height: lanesBottom + AXIS_HEIGHT,
  };
}

/** The top of lane ``index``'s ribbon. */
export function trackTop(index: number): number {
  return index * LANE_HEIGHT + TRACK_TOP;
}

function covers(span: { start_s: number; end_s: number }, time: number | null): boolean {
  if (time === null) return false;
  return span.start_s - SAME_INSTANT_S <= time && time < span.end_s;
}

interface SegmentProps {
  x0: number;
  x1: number;
  top: number;
  fill: string;
  opacity: number;
  /** True while the crosshair is on this span. */
  current: boolean;
  label: string | null;
  labelTone: "light" | "dark";
}

/** One span of a ribbon, inset by half the surface gap on each side once it is wide enough. */
function Segment({ x0, x1, top, fill, opacity, current, label, labelTone }: SegmentProps) {
  const span = x1 - x0;
  const inset = span >= 6 ? 1 : 0;
  const width = Math.max(span - 2 * inset, 1.25);
  const x = x0 + inset;
  return (
    <g>
      <rect
        x={x}
        y={top}
        width={width}
        height={TRACK_HEIGHT}
        rx={Math.min(3, width / 2)}
        fill={fill}
        fillOpacity={opacity}
      />
      {current && (
        <rect
          x={x - 1.5}
          y={top - 1.5}
          width={width + 3}
          height={TRACK_HEIGHT + 3}
          rx={4}
          fill="none"
          className="stroke-foreground"
          strokeOpacity={0.6}
          strokeWidth={1.25}
        />
      )}
      {label !== null && (
        <text
          x={x + width / 2}
          y={top + TRACK_HEIGHT / 2 + 3.5}
          textAnchor="middle"
          fontSize={10}
          fontWeight={500}
          className={labelTone === "light" ? "fill-white" : "fill-neutral-800"}
        >
          {label}
        </text>
      )}
    </g>
  );
}

/** The narrowest span that prints its label: an arrow, or a request's seconds. */
const GLYPH_MIN_PX = 12;
const SECONDS_MIN_PX = 40;

interface LaneRibbonProps {
  lane: MoveABoxClockLane;
  index: number;
  geometry: ClockGeometry;
  time: number | null;
}

/** One operator's round as a ribbon: its waits, its requests and its actions, in time. */
export function LaneRibbon({ lane, index, geometry, time }: LaneRibbonProps) {
  const color = operatorColor(index);
  const top = trackTop(index);
  const segments: ReactNode[] = [];
  lane.waits.forEach((wait, position) => {
    if (wait.end_s - wait.start_s < SAME_INSTANT_S) return;
    segments.push(
      <Segment
        key={`wait-${position}`}
        x0={geometry.xAt(wait.start_s)}
        x1={geometry.xAt(wait.end_s)}
        top={top}
        fill="currentColor"
        opacity={WAITING_OPACITY}
        current={covers(wait, time)}
        label={null}
        labelTone="dark"
      />
    );
  });
  lane.thinking.forEach((span, position) => {
    const x0 = geometry.xAt(span.start_s);
    const x1 = geometry.xAt(span.end_s);
    segments.push(
      <Segment
        key={`think-${position}`}
        x0={x0}
        x1={x1}
        top={top}
        fill={color}
        opacity={1}
        current={covers(span, time)}
        label={x1 - x0 >= SECONDS_MIN_PX ? seconds(span.cost_s) : null}
        labelTone="light"
      />
    );
  });
  lane.actions.forEach((span, position) => {
    const x0 = geometry.xAt(span.start_s);
    const x1 = geometry.xAt(span.end_s);
    const glyph = directionGlyph(span.direction);
    segments.push(
      <Segment
        key={`act-${position}`}
        x0={x0}
        x1={x1}
        top={top}
        fill={color}
        opacity={ACTING_OPACITY}
        current={covers(span, time)}
        label={x1 - x0 >= GLYPH_MIN_PX ? glyph : null}
        labelTone="dark"
      />
    );
  });
  return (
    <g className="text-foreground" aria-label={`${lane.agent_id} on the clock`}>
      {segments}
    </g>
  );
}

/** How far a finish pin's label starts from the pin. */
const PIN_LABEL_GAP = 9;
/** A pin label's average character width at its 10px font, to tell whether it fits. */
const PIN_LABEL_CHAR_PX = 6;

/** Each finish as a pin standing on the ribbon, with the assigned bay it ended on beside it. */
export function FinishPins({ lane, index, geometry }: Omit<LaneRibbonProps, "time">) {
  const color = operatorColor(index);
  const top = trackTop(index);
  return (
    <g>
      {lane.finishes.map((mark, position) => {
        const x = geometry.xAt(mark.at_s);
        const label = finishBay(mark.bay);
        const leftward = x + PIN_LABEL_GAP + label.length * PIN_LABEL_CHAR_PX > geometry.width;
        return (
          <g key={position}>
            <line
              x1={x}
              y1={top - 8}
              x2={x}
              y2={top + TRACK_HEIGHT + 3}
              stroke={color}
              strokeWidth={2}
              strokeLinecap="round"
            />
            <circle
              cx={x}
              cy={top - 10}
              r={4.5}
              fill={color}
              className="stroke-background"
              strokeWidth={2}
            />
            <text
              x={leftward ? x - PIN_LABEL_GAP : x + PIN_LABEL_GAP}
              y={top - 7}
              textAnchor={leftward ? "end" : "start"}
              fontSize={10}
              fontWeight={500}
              className="fill-foreground"
            >
              {label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/**
 * An arrow from the ribbon of the operator whose action landed to the ribbon of
 * the operator whose wait that landing ended, at the instant both happened.
 */
export function WakeLinks({
  lanes,
  geometry,
}: {
  lanes: MoveABoxClockLane[];
  geometry: ClockGeometry;
}) {
  const links: ReactNode[] = [];
  lanes.forEach((lane, index) => {
    lane.waits.forEach((wait, position) => {
      if (wait.cause !== "other_acted" || wait.woken_by === null) return;
      const from = lanes.findIndex(other => other.agent_id === wait.woken_by);
      if (from === -1) return;
      const x = geometry.xAt(wait.end_s);
      const downward = from < index;
      const start = downward ? trackTop(from) + TRACK_HEIGHT + 2 : trackTop(from) - 2;
      const tip = downward ? trackTop(index) - 2 : trackTop(index) + TRACK_HEIGHT + 2;
      const back = downward ? tip - 5 : tip + 5;
      const color = operatorColor(from);
      links.push(
        <g key={`${lane.agent_id}-${position}`}>
          <line
            x1={x}
            y1={start}
            x2={x}
            y2={back}
            stroke={color}
            strokeWidth={1.25}
            strokeOpacity={0.8}
          />
          <path d={`M ${x - 3.5} ${back} L ${x + 3.5} ${back} L ${x} ${tip} Z`} fill={color} />
        </g>
      );
    });
  });
  return <g pointerEvents="none">{links}</g>;
}

interface ClockGridProps {
  ticks: number[];
  geometry: ClockGeometry;
  /** The crosshair's second; tick labels its time chip would cover are left out. */
  time: number | null;
}

/** Whether a tick label at ``x`` would sit under the crosshair's time chip. */
function underChip(x: number, time: number | null, geometry: ClockGeometry): boolean {
  if (time === null) return false;
  return Math.abs(x - geometry.xAt(time)) < CHIP_WIDTH / 2 + 18;
}

/** Hairline gridlines at the ticks behind the ribbons, and the tick labels under them. */
export function ClockGrid({ ticks, geometry, time }: ClockGridProps) {
  const last = ticks.length - 1;
  return (
    <g>
      {ticks.map((tick, position) => {
        const x = geometry.xAt(tick);
        let anchor: "start" | "middle" | "end" = "middle";
        if (position === 0) anchor = "start";
        if (position === last && x > geometry.width - 16) anchor = "end";
        return (
          <g key={tick}>
            <line
              x1={x}
              y1={0}
              x2={x}
              y2={geometry.lanesBottom}
              className="stroke-foreground"
              strokeOpacity={0.06}
              strokeWidth={1}
            />
            {!underChip(x, time, geometry) && (
              <text
                x={x}
                y={geometry.lanesBottom + 15}
                textAnchor={anchor}
                fontSize={10}
                className="fill-muted-foreground tabular-nums"
              >
                {tick}s
              </text>
            )}
          </g>
        );
      })}
      <line
        x1={PLOT_LEFT}
        y1={geometry.lanesBottom}
        x2={geometry.width - PLOT_RIGHT}
        y2={geometry.lanesBottom}
        className="stroke-border"
        strokeWidth={1}
      />
    </g>
  );
}

/** The pointer's second: a hairline through every lane and its time on the axis. */
export function Crosshair({ time, geometry }: { time: number; geometry: ClockGeometry }) {
  const x = geometry.xAt(time);
  const chipX = Math.min(Math.max(x - CHIP_WIDTH / 2, 0), geometry.width - CHIP_WIDTH);
  return (
    <g pointerEvents="none">
      <line
        x1={x}
        y1={0}
        x2={x}
        y2={geometry.lanesBottom}
        className="stroke-foreground"
        strokeOpacity={0.5}
        strokeWidth={1}
      />
      <rect
        x={chipX}
        y={geometry.lanesBottom + 3}
        width={CHIP_WIDTH}
        height={16}
        rx={4}
        className="fill-foreground"
      />
      <text
        x={chipX + CHIP_WIDTH / 2}
        y={geometry.lanesBottom + 14.5}
        textAnchor="middle"
        fontSize={10}
        fontWeight={600}
        className="fill-background tabular-nums"
      >
        {seconds(time)}
      </text>
    </g>
  );
}
