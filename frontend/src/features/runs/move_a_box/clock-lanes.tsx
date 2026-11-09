"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import {
  ACTING_OPACITY,
  ClockGrid,
  clockGeometry,
  Crosshair,
  FinishPins,
  LANE_HEIGHT,
  LaneRibbon,
  PLOT_LEFT,
  WAITING_OPACITY,
  WakeLinks,
} from "./clock-lane-marks";
import {
  clockTicks,
  finishText,
  laneShares,
  momentAt,
  percent,
  seconds,
} from "./clock-lanes-labels";
import { operatorColor } from "./marks";

type MoveABoxRoundClock = components["schemas"]["MoveABoxRoundClock"];
type MoveABoxClockLane = components["schemas"]["MoveABoxClockLane"];

const ZOOMS = [1, 2, 4] as const;
type Zoom = (typeof ZOOMS)[number];

/** The plot's width before the page has measured it, and on a server render. */
const DEFAULT_PLOT_WIDTH = 520;
const MIN_TICK_GAP_PX = 64;

/** The width of the element ``ref`` points at, kept current as it resizes. */
function useMeasuredWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(DEFAULT_PLOT_WIDTH);
  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    const observer = new ResizeObserver(entries => {
      const measured = entries[0]?.contentRect.width;
      if (measured !== undefined && measured > 0) setWidth(measured);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function ZoomSwitch({ zoom, onZoom }: { zoom: Zoom; onZoom: (zoom: Zoom) => void }) {
  return (
    <div
      className="inline-flex rounded-md border border-border p-0.5"
      role="group"
      aria-label="Zoom"
    >
      {ZOOMS.map(level => (
        <button
          key={level}
          type="button"
          aria-pressed={zoom === level}
          onClick={() => onZoom(level)}
          className={cn(
            "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
            zoom === level
              ? "bg-muted text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {level === 1 ? "Fit" : `${level}×`}
        </button>
      ))}
    </div>
  );
}

function Swatch({ children, label }: { children: ReactNode; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width={18} height={12} aria-hidden="true" className="shrink-0 text-foreground">
        {children}
      </svg>
      {label}
    </span>
  );
}

/** A swatch of one tone in every operator's colour, side by side. */
function ToneSwatch({ colors, opacity }: { colors: string[]; opacity: number }) {
  const width = 16 / colors.length;
  return (
    <>
      {colors.map((color, index) => (
        <rect
          key={color}
          x={1 + index * width}
          y={2}
          width={width - 1}
          height={8}
          rx={2}
          fill={color}
          fillOpacity={opacity}
        />
      ))}
    </>
  );
}

/**
 * What each mark means, drawn the way the lanes draw it.
 *
 * Thinking and acting are told apart by tone, so their swatches show that tone
 * in every operator's colour.
 */
function ClockLegend({ laneCount }: { laneCount: number }) {
  const colors = Array.from({ length: laneCount }, (_, index) => operatorColor(index));
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      <Swatch label="Thinking">
        <ToneSwatch colors={colors} opacity={1} />
      </Swatch>
      <Swatch label="Action under way">
        <ToneSwatch colors={colors} opacity={ACTING_OPACITY} />
      </Swatch>
      <Swatch label="Waiting">
        <rect
          x={1}
          y={2}
          width={16}
          height={8}
          rx={2}
          fill="currentColor"
          fillOpacity={WAITING_OPACITY * 1.6}
        />
      </Swatch>
      <Swatch label="Woken by another operator's action">
        <line x1={9} y1={0} x2={9} y2={7} className="stroke-neutral-500" strokeWidth={1.25} />
        <path d="M 5.5 7 L 12.5 7 L 9 12 Z" className="fill-neutral-500" />
      </Swatch>
      <Swatch label="Finished">
        <line x1={9} y1={5} x2={9} y2={12} className="stroke-neutral-500" strokeWidth={2} />
        <circle cx={9} cy={4} r={3.5} className="fill-neutral-500" />
      </Swatch>
    </div>
  );
}

interface LaneLabelProps {
  lane: MoveABoxClockLane;
  index: number;
  duration: number;
}

/** The operator's name, and a thin bar splitting its round into thinking, acting and waiting. */
function LaneLabel({ lane, index, duration }: LaneLabelProps) {
  const color = operatorColor(index);
  const shares = laneShares(lane, duration);
  const parts = [
    { key: "thinking", share: shares.thinking, opacity: 1, fill: color },
    { key: "acting", share: shares.acting, opacity: ACTING_OPACITY, fill: color },
    {
      key: "waiting",
      share: shares.waiting,
      opacity: WAITING_OPACITY * 1.6,
      fill: "currentColor",
    },
  ].filter(part => part.share > 0);
  return (
    <div className="flex flex-col justify-center gap-1 pt-1.5" style={{ height: LANE_HEIGHT }}>
      <div className="flex items-center gap-1.5">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        <span className="truncate text-xs font-medium">{lane.agent_id}</span>
      </div>
      <div className="flex h-1.5 w-full gap-[2px] text-foreground" aria-hidden="true">
        {parts.map(part => (
          <span
            key={part.key}
            className="h-full rounded-full"
            style={{ flexGrow: part.share, backgroundColor: part.fill, opacity: part.opacity }}
          />
        ))}
      </div>
      <span className="truncate text-[10px] tabular-nums text-muted-foreground">
        think {percent(shares.thinking)} · act {percent(shares.acting)} · wait{" "}
        {percent(shares.waiting)}
      </span>
    </div>
  );
}

/** What every operator was doing at the crosshair's second, or how to get a crosshair. */
function ClockReadout({ clock, time }: { clock: MoveABoxRoundClock; time: number | null }) {
  return (
    <div className="mt-2 rounded-md bg-muted/70 px-3 py-2">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 text-[11px] text-muted-foreground">
        {time === null ? (
          <>
            <span>End of the round</span>
            <span className="text-[10px]">Point at the lanes, or use ← →, to read one second</span>
          </>
        ) : (
          <span>
            <span className="font-semibold tabular-nums text-foreground">{seconds(time)}</span> into
            the round
          </span>
        )}
      </div>
      <div className="space-y-0.5">
        {clock.lanes.map((lane, index) => {
          const moment = time === null ? null : momentAt(lane, time);
          const resting = finishText(lane);
          return (
            <div key={lane.agent_id} className="flex min-w-0 items-center gap-2 text-[11px]">
              <span
                className="h-0.5 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: operatorColor(index) }}
              />
              <span className="w-20 shrink-0 truncate text-muted-foreground">{lane.agent_id}</span>
              <span className="shrink-0 font-medium text-foreground">
                {moment?.headline ?? resting}
              </span>
              {moment?.detail && (
                <span className="min-w-0 truncate text-muted-foreground" title={moment.detail}>
                  “{moment.detail}”
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** The crosshair's second after a key, or undefined for a key that does not move it. */
function steppedTime(
  key: string,
  shift: boolean,
  time: number | null,
  duration: number
): number | null | undefined {
  const step = shift ? 10 : 1;
  const from = time ?? 0;
  if (key === "ArrowRight") return Math.min(duration, from + step);
  if (key === "ArrowLeft") return Math.max(0, from - step);
  if (key === "Home") return 0;
  if (key === "End") return duration;
  if (key === "Escape") return null;
  return undefined;
}

/** Every operator's state at ``time``, as the slider's accessible value. */
function valueText(clock: MoveABoxRoundClock, time: number | null): string {
  if (time === null) return "No second chosen";
  const states = clock.lanes.map(lane => `${lane.agent_id} ${momentAt(lane, time).headline}`);
  return `${seconds(time)}: ${states.join("; ")}`;
}

/**
 * Each operator's round on the virtual clock, one ribbon per operator.
 *
 * The axis is virtual seconds since the round started, the time the depot
 * readout showed. Pointing at the lanes, or moving through them with the arrow
 * keys, reads every operator's state at that second below them.
 */
export function ClockLanes({ clock }: { clock: MoveABoxRoundClock }) {
  const [zoom, setZoom] = useState<Zoom>(1);
  const [time, setTime] = useState<number | null>(null);
  const [plotRef, visibleWidth] = useMeasuredWidth();
  const duration = clock.duration_s;
  const geometry = clockGeometry(duration, clock.lanes.length, visibleWidth * zoom);
  const ticks = clockTicks(duration, geometry.pxPerSecond, MIN_TICK_GAP_PX);

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const left = event.currentTarget.getBoundingClientRect().left;
    const at = (event.clientX - left - PLOT_LEFT) / geometry.pxPerSecond;
    setTime(Math.min(Math.max(at, 0), duration));
  }

  function onKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    const next = steppedTime(event.key, event.shiftKey, time, duration);
    if (next === undefined) return;
    event.preventDefault();
    setTime(next);
  }

  return (
    <section
      className="rounded-lg border border-border bg-background p-3"
      aria-label="Virtual clock"
    >
      <header className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Virtual clock</h4>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Seconds into the round · the round ran {Math.round(duration)} s
            {clock.step_duration_s > 0 && ` · each action takes ${clock.step_duration_s} s`}
          </p>
        </div>
        <ZoomSwitch zoom={zoom} onZoom={setZoom} />
      </header>
      <ClockLegend laneCount={clock.lanes.length} />
      <div className="mt-3 flex">
        <div className="w-48 shrink-0 pr-3">
          {clock.lanes.map((lane, index) => (
            <LaneLabel key={lane.agent_id} lane={lane} index={index} duration={duration} />
          ))}
        </div>
        <div ref={plotRef} className="min-w-0 flex-1 overflow-x-auto">
          <svg
            width={geometry.width}
            height={geometry.height}
            className="block rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            role="slider"
            tabIndex={0}
            aria-label="Second of the round"
            aria-valuemin={0}
            aria-valuemax={Math.round(duration)}
            aria-valuenow={time === null ? 0 : Math.round(time)}
            aria-valuetext={valueText(clock, time)}
            onPointerMove={onPointerMove}
            onPointerLeave={() => setTime(null)}
            onKeyDown={onKeyDown}
          >
            <ClockGrid ticks={ticks} geometry={geometry} time={time} />
            {clock.lanes.map((lane, index) => (
              <LaneRibbon
                key={lane.agent_id}
                lane={lane}
                index={index}
                geometry={geometry}
                time={time}
              />
            ))}
            <WakeLinks lanes={clock.lanes} geometry={geometry} />
            {clock.lanes.map((lane, index) => (
              <FinishPins key={lane.agent_id} lane={lane} index={index} geometry={geometry} />
            ))}
            {time !== null && <Crosshair time={time} geometry={geometry} />}
          </svg>
        </div>
      </div>
      <ClockReadout clock={clock} time={time} />
    </section>
  );
}
