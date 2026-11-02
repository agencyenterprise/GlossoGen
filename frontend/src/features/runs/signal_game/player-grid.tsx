"use client";

import { useId } from "react";
import type { components } from "@/types/api.gen";
import { ItemGlyph, StripeDefs, itemPaint, svgIdPrefix } from "./item-glyph";
import { itemColor, itemLabel, sameItem } from "./items";

type SignalGamePlayerSide = components["schemas"]["SignalGamePlayerSide"];
type SignalGameItem = components["schemas"]["SignalGameItem"];

const CELL = 44;
/** A word square is wider than tall, to fit an eight-letter word. */
const WORD_CELL_WIDTH = 72;
const WORD_CELL_HEIGHT = 34;
const PAD = 8;

function isShared(item: SignalGameItem, shared: SignalGameItem[]): boolean {
  return shared.some(other => sameItem(other, item));
}

interface PlayerGridProps {
  side: SignalGamePlayerSide;
  sharedItems: SignalGameItem[];
}

interface SquareProps {
  item: SignalGameItem;
  x: number;
  y: number;
  width: number;
  height: number;
  prefix: string;
}

/** What one square shows: its colour, its shape in its colour and fill, or its word. */
function SquareContent({ item, x, y, width, height, prefix }: SquareProps) {
  if (item.word !== null) {
    return (
      <>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill="transparent"
          className="stroke-border"
          strokeWidth={1}
        />
        <text
          x={x + width / 2}
          y={y + height / 2 + 4}
          textAnchor="middle"
          className="fill-foreground"
          fontSize={11}
          fontFamily="var(--font-mono, ui-monospace, monospace)"
        >
          {item.word}
        </text>
      </>
    );
  }
  const colour = item.colour ?? "unknown";
  const color = itemColor(colour);
  return (
    <>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={item.shape === null ? color : "transparent"}
        fillOpacity={item.shape === null ? 0.85 : 0}
        className="stroke-border"
        strokeWidth={1}
      />
      {item.shape !== null && (
        <ItemGlyph
          shape={item.shape}
          cx={x + width / 2}
          cy={y + height / 2}
          r={Math.min(width, height) * 0.3}
          paint={itemPaint(colour, item.fill, prefix)}
        />
      )}
    </>
  );
}

/**
 * One player's grid as the round left it: the items, the start square and the final one.
 *
 * A colour-only square is filled with its colour; a square with a shape is drawn as
 * that shape in its colour, solid, striped or hollow when the run has fills; a word
 * square shows its word, in a wider square. Squares holding an item that is not on the
 * partner's grid are dimmed, since no player could score there. The start square is
 * tagged S in its corner and the final square is outlined, dashed when the player never
 * called end_round. Both frame the square rather than cover it, so the item stays
 * readable. The moves between them are in the panel's action log, not drawn here.
 */
export function PlayerGrid({ side, sharedItems }: PlayerGridProps) {
  const prefix = svgIdPrefix(useId());
  const rows = side.grid.length;
  const cols = side.grid[0]?.length ?? 0;
  const hasWords = side.grid.some(row => row.some(item => item.word !== null));
  let cellWidth = CELL;
  let cellHeight = CELL;
  if (hasWords) {
    cellWidth = WORD_CELL_WIDTH;
    cellHeight = WORD_CELL_HEIGHT;
  }
  const width = cols * cellWidth + PAD * 2;
  const height = rows * cellHeight + PAD * 2;
  const startX = PAD + (side.start.col - 1) * cellWidth;
  const startY = PAD + (side.start.row - 1) * cellHeight;
  const endX = PAD + (side.final_cell.col - 1) * cellWidth;
  const endY = PAD + (side.final_cell.row - 1) * cellHeight;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Grid of ${side.agent_id}, ${side.steps.length} moves, finished on ${itemLabel(side.final_item)}`}
      className="shrink-0"
    >
      <StripeDefs prefix={prefix} />
      {side.grid.map((row, rowIndex) =>
        row.map((item, colIndex) => {
          const shared = isShared(item, sharedItems);
          return (
            <g key={`${rowIndex}:${colIndex}`} opacity={shared ? 1 : 0.35}>
              <SquareContent
                item={item}
                x={PAD + colIndex * cellWidth}
                y={PAD + rowIndex * cellHeight}
                width={cellWidth}
                height={cellHeight}
                prefix={prefix}
              />
              <title>{`row ${rowIndex + 1}, col ${colIndex + 1}: ${itemLabel(item)}${
                shared ? " (on both grids)" : " (not on the partner's grid)"
              }`}</title>
            </g>
          );
        })
      )}

      <rect
        x={endX + 2}
        y={endY + 2}
        width={cellWidth - 4}
        height={cellHeight - 4}
        rx={4}
        fill="none"
        className="stroke-foreground"
        strokeWidth={3}
        strokeDasharray={side.end_sequence === null ? "4 3" : undefined}
      >
        <title>
          {side.end_sequence === null
            ? `stood here when the round ended: ${itemLabel(side.final_item)}`
            : `finished here (#${side.end_sequence}): ${itemLabel(side.final_item)}`}
        </title>
      </rect>

      <g>
        <rect
          x={startX + 2}
          y={startY + 2}
          width={12}
          height={12}
          rx={3}
          className="fill-foreground"
        />
        <text
          x={startX + 8}
          y={startY + 11}
          textAnchor="middle"
          className="fill-background"
          fontSize={8}
          fontWeight={700}
        >
          S
        </text>
        <title>start</title>
      </g>
    </svg>
  );
}
