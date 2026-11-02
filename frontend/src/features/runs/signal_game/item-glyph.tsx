"use client";

/**
 * A signal_game item drawn in SVG: its shape, in its colour, with its fill.
 *
 * The shapes and fills are the scenario's own names. A shape the panel does not know
 * is drawn as a small square with the name in its tooltip, so a new shape shows up
 * rather than vanishing. Striped fills reference a hatch pattern per colour, which
 * ``StripeDefs`` declares once per drawing under an id prefix unique to that drawing.
 */

import { ITEM_COLORS, itemColor } from "./items";

/** How a shape's body and outline are painted. */
interface Paint {
  fill: string;
  stroke: string;
  strokeWidth: number;
}

function stripeId(prefix: string, colour: string): string {
  return `${prefix}-stripe-${colour}`;
}

/** An id prefix safe inside ``url(#...)``, from React's ``useId`` value. */
export function svgIdPrefix(reactId: string): string {
  return `sg${reactId.replace(/[^A-Za-z0-9_-]/g, "")}`;
}

/** One diagonal hatch pattern per palette colour (and one for unknown colours). */
export function StripeDefs({ prefix }: { prefix: string }) {
  const colours = [...Object.keys(ITEM_COLORS), "unknown"];
  return (
    <defs>
      {colours.map(colour => (
        <pattern
          key={colour}
          id={stripeId(prefix, colour)}
          width={4}
          height={4}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width={4} height={4} fill="var(--background, #fff)" />
          <rect width={2} height={4} fill={itemColor(colour)} />
        </pattern>
      ))}
    </defs>
  );
}

/** The paint for an item of ``colour`` with ``fillStyle`` (null: no fills in the run). */
export function itemPaint(colour: string, fillStyle: string | null, prefix: string): Paint {
  const color = itemColor(colour);
  if (fillStyle === "hollow") {
    return { fill: "var(--background, #fff)", stroke: color, strokeWidth: 2 };
  }
  if (fillStyle === "striped") {
    const known = colour in ITEM_COLORS;
    const patternColour = known ? colour : "unknown";
    return { fill: `url(#${stripeId(prefix, patternColour)})`, stroke: color, strokeWidth: 1.5 };
  }
  return { fill: color, stroke: "var(--background, #fff)", strokeWidth: 1 };
}

interface ItemGlyphProps {
  shape: string;
  cx: number;
  cy: number;
  /** Half the glyph's width. */
  r: number;
  paint: Paint;
}

function starPoints(cx: number, cy: number, r: number): string {
  const points: string[] = [];
  for (let index = 0; index < 10; index += 1) {
    let radius = r * 0.45;
    if (index % 2 === 0) radius = r;
    const angle = -Math.PI / 2 + (index * Math.PI) / 5;
    points.push(`${cx + radius * Math.cos(angle)},${cy + radius * Math.sin(angle)}`);
  }
  return points.join(" ");
}

export function ItemGlyph({ shape, cx, cy, r, paint }: ItemGlyphProps) {
  const { fill, stroke, strokeWidth } = paint;
  switch (shape) {
    case "circle":
      return (
        <circle
          cx={cx}
          cy={cy}
          r={r * 0.85}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      );
    case "triangle":
      return (
        <polygon
          points={`${cx},${cy - r} ${cx + r},${cy + r * 0.8} ${cx - r},${cy + r * 0.8}`}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinejoin="round"
        />
      );
    case "star":
      return (
        <polygon
          points={starPoints(cx, cy, r)}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinejoin="round"
        />
      );
    case "diamond":
      return (
        <polygon
          points={`${cx},${cy - r} ${cx + r * 0.8},${cy} ${cx},${cy + r} ${cx - r * 0.8},${cy}`}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      );
    case "cross": {
      const arm = r * 0.35;
      return (
        <path
          d={`M${cx - arm},${cy - r} h${2 * arm} v${r - arm} h${r - arm} v${2 * arm} h${-(r - arm)} v${r - arm} h${-2 * arm} v${-(r - arm)} h${-(r - arm)} v${-2 * arm} h${r - arm} z`}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      );
    }
    case "heart":
      return (
        <path
          d={`M${cx},${cy + r * 0.9} C${cx - r * 1.4},${cy - r * 0.1} ${cx - r * 0.6},${cy - r * 1.2} ${cx},${cy - r * 0.35} C${cx + r * 0.6},${cy - r * 1.2} ${cx + r * 1.4},${cy - r * 0.1} ${cx},${cy + r * 0.9} z`}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      );
    default:
      return (
        <rect
          x={cx - r * 0.7}
          y={cy - r * 0.7}
          width={r * 1.4}
          height={r * 1.4}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        >
          <title>{shape}</title>
        </rect>
      );
  }
}
