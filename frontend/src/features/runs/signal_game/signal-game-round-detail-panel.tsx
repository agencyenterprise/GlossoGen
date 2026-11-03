"use client";

import type { components } from "@/types/api.gen";
import { isScenarioExtras } from "../scenario-plugin";
import { useId } from "react";
import { ItemGlyph, StripeDefs, itemPaint, svgIdPrefix } from "./item-glyph";
import {
  actionLog,
  cellLabel,
  itemColor,
  itemLabel,
  playerLetter,
  sameItem,
  type ActionGroup,
} from "./items";
import { PlayerGrid } from "./player-grid";

type SignalGameRound = components["schemas"]["SignalGameRound"];
type SignalGamePlayerSide = components["schemas"]["SignalGamePlayerSide"];
type SignalGameItem = components["schemas"]["SignalGameItem"];

/** A small swatch for a coloured item, beside its name. A word has none. */
function ItemSwatch({ item }: { item: SignalGameItem }) {
  const colour = item.colour ?? "unknown";
  const color = itemColor(colour);
  const prefix = svgIdPrefix(useId());
  return (
    <svg width={12} height={12} aria-hidden="true" className="inline-block shrink-0 align-[-1px]">
      {item.fill === "striped" && <StripeDefs prefix={prefix} />}
      {item.shape === null ? (
        <rect x={0.5} y={0.5} width={11} height={11} rx={2} fill={color} />
      ) : (
        <ItemGlyph
          shape={item.shape}
          cx={6}
          cy={6}
          r={5}
          paint={itemPaint(colour, item.fill, prefix)}
        />
      )}
    </svg>
  );
}

function ItemName({ item }: { item: SignalGameItem }) {
  return (
    <span className="inline-flex items-center gap-1">
      {item.word === null && <ItemSwatch item={item} />}
      {itemLabel(item)}
    </span>
  );
}

function OutcomeBadge({ round }: { round: SignalGameRound }) {
  if (round.success === null) {
    return (
      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        not resolved
      </span>
    );
  }
  return (
    <span
      className={
        round.success
          ? "rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800"
          : "rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
      }
    >
      {round.success ? "point" : "no point"}
    </span>
  );
}

function PlayerColumn({ side, round }: { side: SignalGamePlayerSide; round: SignalGameRound }) {
  const partner = round.players.find(other => other.agent_id !== side.agent_id) ?? null;
  const matched = partner !== null && sameItem(side.final_item, partner.final_item);
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline gap-2">
        <span className="text-xs font-medium">{side.agent_id}</span>
        <span className="text-[10px] text-muted-foreground">
          {side.steps.length} moves
          {side.end_sequence === null ? " · never called end_round" : ""}
        </span>
      </div>
      <PlayerGrid side={side} sharedItems={round.shared_items} />
      <div className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
        <div className={matched ? "text-emerald-700" : undefined}>
          finished on <ItemName item={side.final_item} /> at {cellLabel(side.final_cell)}
        </div>
        {side.colour_order.length > 0 && <div>colours listed: {side.colour_order.join(", ")}</div>}
        {side.shape_order.length > 0 && <div>shapes listed: {side.shape_order.join(", ")}</div>}
        {side.fill_order.length > 0 && <div>fills listed: {side.fill_order.join(", ")}</div>}
      </div>
    </div>
  );
}

function sequenceLabel(group: ActionGroup): string {
  if (group.firstSequence === group.lastSequence) return `#${group.firstSequence}`;
  return `#${group.firstSequence}–${group.lastSequence}`;
}

/** Both players' actions in the round's numbering: one line per run of a player's steps
 *  with the same reasoning (usually one move call), and one per end_round. */
function ActionLog({ round }: { round: SignalGameRound }) {
  const groups = actionLog(round.players);
  if (groups.length === 0) {
    return <div className="text-[11px] text-muted-foreground">No moves this round.</div>;
  }
  return (
    <ol className="space-y-1 text-[11px]">
      {groups.map(group => (
        <li
          key={`${group.agentId}:${group.firstSequence}`}
          className="grid grid-cols-[4.5rem_1rem_minmax(0,11rem)_minmax(0,1fr)] gap-x-2"
        >
          <span className="font-mono text-muted-foreground">{sequenceLabel(group)}</span>
          <span className="font-mono font-semibold">{playerLetter(group.agentId)}</span>
          <span className="font-mono">
            {group.kind === "end" ? "end_round" : group.directions.join(" ")}
            <span className="text-muted-foreground"> → {cellLabel(group.cell)}</span>
          </span>
          <span className="text-muted-foreground">{group.reasoning ?? ""}</span>
        </li>
      ))}
    </ol>
  );
}

interface SignalGameRoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/**
 * signal_game grids and actions for one round, rendered above the round timeline.
 *
 * Each player's grid shows where its figure started and where it finished. Items that
 * are not on both grids are dimmed: the shared ones are the ground truth neither player
 * saw. The log below interleaves both players' moves in the order they happened, with
 * the private sentence each gave, which is where a signal shows up as a signal.
 */
export function SignalGameRoundDetailPanel({
  roundNumber,
  extras,
}: SignalGameRoundDetailPanelProps) {
  if (!isScenarioExtras(extras, "signal_game")) return null;
  const round = extras.cases.find(entry => entry.round_number === roundNumber) ?? null;
  if (round === null) return null;

  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Round {round.round_number}
        </span>
        <OutcomeBadge round={round} />
        <span className="ml-auto text-[11px] text-muted-foreground">
          chance {Math.round(round.chance * 100)}%
        </span>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        <span className="font-medium text-foreground">on both grids:</span>
        {round.shared_items.map(item => (
          <ItemName key={itemLabel(item)} item={item} />
        ))}
      </div>

      <div className="mb-3 flex flex-wrap gap-6">
        {round.players.map(side => (
          <PlayerColumn key={side.agent_id} side={side} round={round} />
        ))}
      </div>

      <div className="mb-1 text-[10px] text-muted-foreground">
        S = start · outlined = final square (dashed: no end_round) · dimmed = not on the
        partner&apos;s grid
      </div>

      <ActionLog round={round} />
    </div>
  );
}
