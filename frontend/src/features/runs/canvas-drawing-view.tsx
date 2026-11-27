import type { components } from "@/types/api.gen";

type CanvasDrawing = components["schemas"]["CanvasDrawing"];

/** Longest side of a drawing on the page, in CSS pixels. */
const DRAWING_SIDE_PX = 192;

/** A message sent as a canvas drawing: its painted pixels black on white,
 *  separated by thin grid lines, as the recipient's image shows them. The
 *  colors stay the same in dark mode so the page matches what the agent saw. */
export function CanvasDrawingView({ drawing }: { drawing: CanvasDrawing }) {
  const { width, height, pixels } = drawing;
  const scale = DRAWING_SIDE_PX / Math.max(width, height);
  const columns = Array.from({ length: width + 1 }, (_, index) => index);
  const rows = Array.from({ length: height + 1 }, (_, index) => index);
  return (
    <figure className="mt-0.5">
      <svg
        role="img"
        aria-label={`Drawing of ${pixels.length} pixels on a ${width}x${height} canvas`}
        viewBox={`0 0 ${width} ${height}`}
        width={width * scale}
        height={height * scale}
        shapeRendering="crispEdges"
        className="rounded-sm border border-border"
      >
        <rect x={0} y={0} width={width} height={height} fill="#ffffff" />
        {pixels.map(pixel => (
          <rect
            key={`${pixel.x},${pixel.y}`}
            x={pixel.x}
            y={pixel.y}
            width={1}
            height={1}
            fill="#000000"
          />
        ))}
        {columns.map(column => (
          <line
            key={`column-${column}`}
            x1={column}
            y1={0}
            x2={column}
            y2={height}
            stroke="#c8c8c8"
            strokeWidth={1 / scale}
          />
        ))}
        {rows.map(row => (
          <line
            key={`row-${row}`}
            x1={0}
            y1={row}
            x2={width}
            y2={row}
            stroke="#c8c8c8"
            strokeWidth={1 / scale}
          />
        ))}
      </svg>
      <figcaption className="mt-0.5 text-[10px] text-muted-foreground/60">
        {pixels.length.toLocaleString()} {pixels.length === 1 ? "pixel" : "pixels"} · {width}x
        {height} canvas
      </figcaption>
    </figure>
  );
}
