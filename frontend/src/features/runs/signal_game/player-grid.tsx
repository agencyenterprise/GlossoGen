"use client";

import { useId } from "react";
import type { components } from "@/types/api.gen";
import { ItemGlyph, StripeDefs, itemPaint, svgIdPrefix } from "./item-glyph";
import { itemColor, itemLabel, sameItem } from "./items";

type SignalGamePlayerSide = components["schemas"]["SignalGamePlayerSide"];
type SignalGameItem = components["schemas"]["SignalGameItem"];

const CELL = 44;
const PAD = 8;

function isShared(item: SignalGameItem, shared: SignalGameItem[]): boolean {
  return shared.some(other => sameItem(other, item));
}

interface PlayerGridProps {
  side: SignalGamePlayerSide;
  sharedItems: SignalGameItem[];
}

/**
 * One player's grid as the round left it: the items, the start square and the final one.
 *
 * A colour-only square is filled with its colour; a square with a shape is drawn as
 * that shape in its colour, solid, striped or hollow when the run has fills. Squares holding an item that is not on the partner's grid
 * are dimmed, since no player could score there. The start square is tagged S in its
 * corner and the final square is outlined, dashed when the player never called
 * end_round. Both frame the square rather than cover it, so the item stays readable.
 * The moves between them are in the panel's action log, not drawn here.
 */
export function PlayerGrid({ side, sharedItems }: PlayerGridProps) {
  const prefix = svgIdPrefix(useId());
  const size = side.grid.length;
  const width = size * CELL + PAD * 2;
  const startX = PAD + (side.start.col - 1) * CELL;
  const startY = PAD + (side.start.row - 1) * CELL;
  const endX = PAD + (side.final_cell.col - 1) * CELL;
  const endY = PAD + (side.final_cell.row - 1) * CELL;

  return (
    <svg
      width={width}
      height={width}
      viewBox={`0 0 ${width} ${width}`}
      role="img"
      aria-label={`Grid of ${side.agent_id}, ${side.steps.length} moves, finished on ${itemLabel(side.final_item)}`}
      className="shrink-0"
    >
      <StripeDefs prefix={prefix} />
      {side.grid.map((row, rowIndex) =>
        row.map((item, colIndex) => {
          const x = PAD + colIndex * CELL;
          const y = PAD + rowIndex * CELL;
          const shared = isShared(item, sharedItems);
          const color = itemColor(item.colour);
          return (
            <g key={`${rowIndex}:${colIndex}`} opacity={shared ? 1 : 0.35}>
              <rect
                x={x}
                y={y}
                width={CELL}
                height={CELL}
                fill={item.shape === null ? color : "transparent"}
                fillOpacity={item.shape === null ? 0.85 : 0}
                className="stroke-border"
                strokeWidth={1}
              />
              {item.shape !== null && (
                <ItemGlyph
                  shape={item.shape}
                  cx={x + CELL / 2}
                  cy={y + CELL / 2}
                  r={CELL * 0.3}
                  paint={itemPaint(item.colour, item.fill, prefix)}
                />
              )}
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
        width={CELL - 4}
        height={CELL - 4}
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
