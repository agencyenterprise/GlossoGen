"use client";

import { useState, type MouseEvent, type ReactNode } from "react";
import type { components } from "@/types/api.gen";
import { humanize } from "../format";
import type { RoundDetailPanelProps } from "../scenario-plugin";
import { TeamResultPill } from "../team-result-pill";
import {
  axisTicks,
  linePath,
  symmetricRange,
  tickAtX,
  tickX,
  valueAt,
  valueY,
  zeroBars,
  type PlotBox,
  type ValueRange,
} from "./waveform-geometry";

type CarrierExtras = components["schemas"]["CarrierSongRunExtras"];
type CarrierRound = components["schemas"]["CarrierSongCaseSummary"];
type HoverHandler = (tick: number | null) => void;

const VIEW_WIDTH = 640;
const PLOT_LEFT = 30;
const PLOT_WIDTH = 604;
const PLOT_TOP = 6;
const SIGNAL_HEIGHT = 110;
const STRIP_HEIGHT = 36;
const AXIS_ROOM = 16;

const SONG_COLOUR = "var(--series-other)";
const RECORDING_COLOUR = "var(--series-1)";
const NOISE_COLOUR = "var(--series-2)";
const CHANNEL_COLOUR = "var(--series-other)";

function isCarrierExtras(extras: unknown): extras is CarrierExtras {
  if (typeof extras !== "object" || extras === null) return false;
  return (extras as { scenario_name?: string }).scenario_name === "carrier_song";
}

function signed(value: number): string {
  if (value > 0) return `+${value}`;
  return String(value);
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}

function CodeCells({
  label,
  chars,
  mismatched,
}: {
  label: string;
  chars: string[];
  mismatched: boolean[];
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 text-[11px] text-muted-foreground">{label}</span>
      <div className="flex gap-1">
        {chars.map((char, index) => (
          <span
            key={index}
            className={`flex h-7 w-6 items-center justify-center rounded border font-mono text-[13px] ${
              mismatched[index]
                ? "border-rose-500/40 bg-rose-500/15 text-rose-700 dark:text-rose-400"
                : "border-border bg-background"
            }`}
          >
            {char}
          </span>
        ))}
      </div>
    </div>
  );
}

function CodeComparison({ secret, decoded }: { secret: string; decoded: string | null }) {
  const sent = [...secret];
  return (
    <div className="space-y-1.5">
      <CodeCells label="code sent" chars={sent} mismatched={sent.map(() => false)} />
      {decoded === null ? (
        <div className="flex items-center gap-2">
          <span className="w-16 text-[11px] text-muted-foreground">decoded</span>
          <span className="text-[11px] italic text-muted-foreground">no decoding submitted</span>
        </div>
      ) : (
        <CodeCells
          label="decoded"
          chars={[...decoded]}
          mismatched={[...decoded].map((char, index) => char !== sent[index])}
        />
      )}
    </div>
  );
}

function ChartFrame({
  label,
  height,
  count,
  range,
  showAxis,
  hoverTick,
  onHover,
  children,
}: {
  label: string;
  height: number;
  count: number;
  range: ValueRange;
  showAxis: boolean;
  hoverTick: number | null;
  onHover: HoverHandler;
  children: (box: PlotBox) => ReactNode;
}) {
  const box: PlotBox = { left: PLOT_LEFT, top: PLOT_TOP, width: PLOT_WIDTH, height };
  const bottom = box.top + box.height;
  const viewHeight = bottom + (showAxis ? AXIS_ROOM : 4);
  function handleMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) * VIEW_WIDTH) / rect.width;
    onHover(tickAtX(x, count, box));
  }
  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} ${viewHeight}`}
      className="block w-full"
      role="img"
      aria-label={label}
      onMouseMove={handleMove}
      onMouseLeave={() => onHover(null)}
    >
      {axisTicks(count).map(tick => (
        <line
          key={tick}
          x1={tickX(tick, count, box)}
          x2={tickX(tick, count, box)}
          y1={box.top}
          y2={bottom}
          className="stroke-border"
          strokeWidth={1}
        />
      ))}
      <line
        x1={box.left}
        x2={box.left + box.width}
        y1={valueY(0, range, box)}
        y2={valueY(0, range, box)}
        className="stroke-muted-foreground/40"
        strokeWidth={1}
      />
      {[range.max, 0, range.min].map(value => (
        <text
          key={value}
          x={box.left - 6}
          y={valueY(value, range, box) + 3}
          textAnchor="end"
          className="fill-muted-foreground text-[10px]"
        >
          {value}
        </text>
      ))}
      {children(box)}
      {hoverTick !== null ? (
        <line
          x1={tickX(hoverTick, count, box)}
          x2={tickX(hoverTick, count, box)}
          y1={box.top}
          y2={bottom}
          className="stroke-foreground/50"
          strokeWidth={1}
        />
      ) : null}
      {showAxis
        ? axisTicks(count).map(tick => (
            <text
              key={tick}
              x={tickX(tick, count, box)}
              y={bottom + 12}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {tick}
            </text>
          ))
        : null}
    </svg>
  );
}

function BarStrip({
  values,
  range,
  box,
  colour,
}: {
  values: number[];
  range: ValueRange;
  box: PlotBox;
  colour: string;
}) {
  return (
    <>
      {zeroBars(values, range, box).map(bar => (
        <rect
          key={bar.tick}
          x={bar.x}
          y={bar.y}
          width={bar.width}
          height={bar.height}
          rx={1}
          style={{ fill: colour }}
        />
      ))}
    </>
  );
}

function LegendSwatch({ colour, label }: { colour: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-0.5 w-4 rounded" style={{ background: colour }} />
      {label}
    </span>
  );
}

function Readout({ round, tick }: { round: CarrierRound; tick: number | null }) {
  if (tick === null) {
    return <span>Hover over the charts to read a tick.</span>;
  }
  const parts = [`tick ${tick}`, `song ${valueAt(round.song, tick)}`];
  if (round.noise !== null && round.recording !== null) {
    parts.push(
      `sender's noise ${signed(valueAt(round.noise, tick))}`,
      `channel noise ${signed(valueAt(round.channel_noise, tick))}`,
      `heard ${valueAt(round.recording, tick)}`
    );
  }
  return <span className="font-mono">{parts.join(" · ")}</span>;
}

function Waveforms({ round }: { round: CarrierRound }) {
  const [hoverTick, setHoverTick] = useState<number | null>(null);
  const count = round.song.length;
  const heard = round.recording;
  const noise = round.noise;
  const signalRange = symmetricRange(heard === null ? [round.song] : [round.song, heard], 1);
  const stripRange = symmetricRange(noise === null ? [] : [noise, round.channel_noise], 1);
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <LegendSwatch colour={SONG_COLOUR} label="song (only the sender reads it)" />
          {heard !== null ? (
            <LegendSwatch colour={RECORDING_COLOUR} label="recording (what the receiver hears)" />
          ) : null}
        </div>
        <ChartFrame
          label="The round's song and the recording the receiver heard"
          height={SIGNAL_HEIGHT}
          count={count}
          range={signalRange}
          showAxis={noise === null}
          hoverTick={hoverTick}
          onHover={setHoverTick}
        >
          {box => (
            <>
              <path
                d={linePath(round.song, signalRange, box)}
                fill="none"
                strokeWidth={2}
                style={{ stroke: SONG_COLOUR }}
              />
              {heard !== null ? (
                <path
                  d={linePath(heard, signalRange, box)}
                  fill="none"
                  strokeWidth={2}
                  style={{ stroke: RECORDING_COLOUR }}
                />
              ) : null}
            </>
          )}
        </ChartFrame>
      </div>
      {noise === null ? (
        <div className="text-[11px] italic text-muted-foreground">
          The sender never ended its turn, so nothing was transmitted.
        </div>
      ) : (
        <>
          <div>
            <SectionLabel>Noise the sender added</SectionLabel>
            <ChartFrame
              label="The noise the sender's executor added to the song"
              height={STRIP_HEIGHT}
              count={count}
              range={stripRange}
              showAxis={false}
              hoverTick={hoverTick}
              onHover={setHoverTick}
            >
              {box => (
                <BarStrip values={noise} range={stripRange} box={box} colour={NOISE_COLOUR} />
              )}
            </ChartFrame>
          </div>
          <div>
            <SectionLabel>Channel noise</SectionLabel>
            <ChartFrame
              label="The channel noise added to the recording"
              height={STRIP_HEIGHT}
              count={count}
              range={stripRange}
              showAxis={true}
              hoverTick={hoverTick}
              onHover={setHoverTick}
            >
              {box => (
                <BarStrip
                  values={round.channel_noise}
                  range={stripRange}
                  box={box}
                  colour={CHANNEL_COLOUR}
                />
              )}
            </ChartFrame>
          </div>
        </>
      )}
      <div className="text-[11px] text-muted-foreground">
        <Readout round={round} tick={hoverTick} />
      </div>
    </div>
  );
}

function ExecutorSource({ round }: { round: CarrierRound }) {
  if (round.noise === null) return null;
  if (round.executor_code === null) {
    return (
      <div className="text-[11px] italic text-muted-foreground">The sender played silence.</div>
    );
  }
  return (
    <details>
      <summary className="cursor-pointer text-[11px] text-muted-foreground">
        Executor that produced this noise
      </summary>
      <pre className="mt-1.5 overflow-x-auto rounded border border-border/60 bg-background p-2 font-mono text-[11px] leading-relaxed">
        {round.executor_code}
      </pre>
    </details>
  );
}

/** carrier_song per-round detail rendered at the top of the round-timeline modal. */
export function CarrierSongRoundDetailPanel({
  roundNumber,
  extras,
  roundResults,
}: RoundDetailPanelProps) {
  if (!isCarrierExtras(extras)) return null;
  const round = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (round === null) return null;
  const result = roundResults[0] ?? null;

  return (
    <div className="mb-5 space-y-3 rounded-lg border border-border bg-muted/40 p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Round {round.round_number}
        </span>
        <span className="text-sm font-medium">
          {humanize(round.sender_id)} sends, {humanize(round.receiver_id)} decodes
        </span>
        <span className="ml-auto">
          <TeamResultPill result={result} />
        </span>
      </div>
      <CodeComparison secret={round.secret} decoded={round.decoded} />
      <Waveforms round={round} />
      <ExecutorSource round={round} />
    </div>
  );
}
