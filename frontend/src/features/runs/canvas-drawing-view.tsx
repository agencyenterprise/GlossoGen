import type { components } from "@/types/api.gen";

type CanvasDrawing = components["schemas"]["CanvasDrawing"];

/** Smallest and largest longest side of a drawing on the page, in CSS pixels. */
const MIN_DRAWING_SIDE_PX = 192;
const MAX_DRAWING_SIDE_PX = 512;
/** Each canvas pixel gets at least this many CSS pixels while the drawing fits. */
const PREFERRED_CELL_PX = 2;
/** Grid lines are drawn only when a cell is at least this wide, so they never cover the drawing. */
const MIN_CELL_PX_FOR_GRID = 4;

/** A message sent as a canvas drawing: its painted pixels black on white, as
 *  the recipient's image shows them. Thin grid lines separate the cells when
 *  the cells are large enough to show them. The colors stay the same in dark
 *  mode so the page matches what the agent saw. */
export function CanvasDrawingView({ drawing }: { drawing: CanvasDrawing }) {
  const { width, height, pixels } = drawing;
  const longestSide = Math.max(width, height);
  const sidePx = Math.min(
    MAX_DRAWING_SIDE_PX,
    Math.max(MIN_DRAWING_SIDE_PX, longestSide * PREFERRED_CELL_PX)
  );
  const scale = sidePx / longestSide;
  const showGrid = scale >= MIN_CELL_PX_FOR_GRID;
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
        className="max-w-full rounded-sm border border-border"
      >
        <rect x={0} y={0} width={width} height={height} fill="#ffffff" />
        {showGrid
          ? columns.map(column => (
              <line
                key={`column-${column}`}
                x1={column}
                y1={0}
                x2={column}
                y2={height}
                stroke="#c8c8c8"
                strokeWidth={1 / scale}
              />
            ))
          : null}
        {showGrid
          ? rows.map(row => (
              <line
                key={`row-${row}`}
                x1={0}
                y1={row}
                x2={width}
                y2={row}
                stroke="#c8c8c8"
                strokeWidth={1 / scale}
              />
            ))
          : null}
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
      </svg>
      <figcaption className="mt-0.5 text-[10px] text-muted-foreground/60">
        {pixels.length.toLocaleString()} {pixels.length === 1 ? "pixel" : "pixels"} · {width}x
        {height} canvas
      </figcaption>
    </figure>
  );
}
