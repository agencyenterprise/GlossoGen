"use client";

import { useState, type MouseEvent, type ReactNode } from "react";
import type { components } from "@/types/api.gen";
import { humanize } from "../format";
import type { RoundDetailPanelProps } from "../scenario-plugin";
import { colorHex } from "../shape-glyphs";
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

type CarrierExtras = components["schemas"]["SignalGameCarrierRunExtras"];
type CarrierRound = components["schemas"]["SignalGameCarrierCaseSummary"];
type PlayerRound = components["schemas"]["SignalGameCarrierPlayerRound"];
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
const PLAYER_COLOURS = ["var(--series-2)", "var(--series-3)"];
const CHANNEL_COLOUR = "var(--series-other)";

function isCarrierExtras(extras: unknown): extras is CarrierExtras {
  if (typeof extras !== "object" || extras === null) return false;
  return (extras as { scenario_name?: string }).scenario_name === "signal_game_carrier";
}

function signed(value: number): string {
  if (value > 0) return `+${value}`;
  return String(value);
}

function playerColour(index: number): string {
  return PLAYER_COLOURS[index] ?? "var(--series-other)";
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}

function GridCell({ colour, picked }: { colour: string; picked: boolean }) {
  return (
    <div
      title={colour}
      className={`flex aspect-square items-center justify-center rounded-[2px] ${
        picked ? "ring-2 ring-foreground" : ""
      }`}
      style={{ background: colorHex(colour) }}
    />
  );
}

function PlayerGrid({ player, index }: { player: PlayerRound; index: number }) {
  const picked = player.square;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline gap-1.5">
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ background: playerColour(index) }}
        />
        <span className="truncate text-[11px] font-medium">{humanize(player.agent_id)}</span>
      </div>
      <div className="inline-grid gap-px rounded-md border border-border bg-muted/20 p-1">
        {player.grid.map((row, rowIndex) => (
          <div key={rowIndex} className="flex gap-px">
            {row.map((colour, colIndex) => (
              <div key={colIndex} className="w-7">
                <GridCell
                  colour={colour}
                  picked={
                    picked !== null && picked[0] === rowIndex + 1 && picked[1] === colIndex + 1
                  }
                />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground">
        {player.colour === null ? (
          <span className="italic">picked nothing</span>
        ) : (
          <>
            picked <span className="font-mono">{player.colour}</span>
          </>
        )}
      </div>
    </div>
  );
}

function Grids({ round }: { round: CarrierRound }) {
  return (
    <div>
      <SectionLabel>Each player&apos;s own grid, with the square it picked ringed</SectionLabel>
      <div className="flex flex-wrap gap-6">
        {round.players.map((player, index) => (
          <PlayerGrid key={player.agent_id} player={player} index={index} />
        ))}
      </div>
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
  for (const player of round.players) {
    if (player.noise !== null) {
      parts.push(`${humanize(player.agent_id)} ${signed(valueAt(player.noise, tick))}`);
    }
  }
  parts.push(`channel noise ${signed(valueAt(round.channel_noise, tick))}`);
  if (round.recording !== null) {
    parts.push(`recording ${valueAt(round.recording, tick)}`);
  }
  return <span className="font-mono">{parts.join(" · ")}</span>;
}

function Waveforms({ round }: { round: CarrierRound }) {
  const [hoverTick, setHoverTick] = useState<number | null>(null);
  const count = round.song.length;
  const heard = round.recording;
  const transmitted = round.players.filter(player => player.noise !== null);
  const signalRange = symmetricRange(heard === null ? [round.song] : [round.song, heard], 1);
  const stripRange = symmetricRange(
    [...transmitted.map(player => player.noise ?? []), round.channel_noise],
    1
  );
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <LegendSwatch colour={SONG_COLOUR} label="song (the round's sound, before any noise)" />
          {heard !== null ? (
            <LegendSwatch
              colour={RECORDING_COLOUR}
              label="recording, what both players hear (song + both players' noise + channel noise)"
            />
          ) : null}
        </div>
        <ChartFrame
          label="The round's song and the recording both players heard"
          height={SIGNAL_HEIGHT}
          count={count}
          range={signalRange}
          showAxis={transmitted.length === 0}
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
      {round.players.map((player, index) =>
        player.noise === null ? (
          <div key={player.agent_id} className="text-[11px] italic text-muted-foreground">
            {humanize(player.agent_id)} never transmitted.
          </div>
        ) : (
          <div key={player.agent_id}>
            <SectionLabel>Noise {humanize(player.agent_id)} added to the song</SectionLabel>
            <ChartFrame
              label={`The noise ${player.agent_id}'s executor added to the song`}
              height={STRIP_HEIGHT}
              count={count}
              range={stripRange}
              showAxis={false}
              hoverTick={hoverTick}
              onHover={setHoverTick}
            >
              {box => (
                <BarStrip
                  values={player.noise ?? []}
                  range={stripRange}
                  box={box}
                  colour={playerColour(index)}
                />
              )}
            </ChartFrame>
          </div>
        )
      )}
      <div>
        <SectionLabel>Channel noise, added by the world and chosen by neither player</SectionLabel>
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
      <div className="text-[11px] text-muted-foreground">
        <Readout round={round} tick={hoverTick} />
      </div>
    </div>
  );
}

function Executors({ round }: { round: CarrierRound }) {
  const written = round.players.filter(player => player.executor_code !== null);
  if (written.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {written.map(player => (
        <details key={player.agent_id}>
          <summary className="cursor-pointer text-[11px] text-muted-foreground">
            Executor {humanize(player.agent_id)} played this round
          </summary>
          <pre className="mt-1.5 overflow-x-auto rounded border border-border/60 bg-background p-2 font-mono text-[11px] leading-relaxed">
            {player.executor_code}
          </pre>
        </details>
      ))}
    </div>
  );
}

/** signal_game_carrier per-round detail rendered at the top of the round-timeline modal. */
export function SignalGameCarrierRoundDetailPanel({
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
        <span className="text-sm font-medium">Both players transmit, then each picks a square</span>
        <span className="ml-auto">
          <TeamResultPill result={result} />
        </span>
      </div>
      <Grids round={round} />
      <Waveforms round={round} />
      <Executors round={round} />
    </div>
  );
}
