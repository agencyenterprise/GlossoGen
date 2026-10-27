/**
 * Geometry for carrier_song's round waveforms: where each tick sits, how a value
 * maps to a height, and the SVG paths and bars the round panel draws.
 */

/** The plotting area of one chart, in SVG user units. */
export interface PlotBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The values a chart's height spans, `max` at the top. */
export interface ValueRange {
  min: number;
  max: number;
}

/** One bar of a bar strip, in SVG user units. */
export interface Bar {
  tick: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The value at `tick`; throws when `tick` is outside `values`, which a clamped tick never is. */
export function valueAt(values: number[], tick: number): number {
  const value = values[tick];
  if (value === undefined) {
    throw new RangeError(`tick ${tick} is outside ${values.length} values`);
  }
  return value;
}

/** The x of the centre of `tick`'s slot, for `count` ticks across `box`. */
export function tickX(tick: number, count: number, box: PlotBox): number {
  return box.left + ((tick + 0.5) * box.width) / count;
}

/** The y of `value` within `range`: the top of `box` for `range.max`, the bottom for `range.min`. */
export function valueY(value: number, range: ValueRange, box: PlotBox): number {
  return box.top + ((range.max - value) / (range.max - range.min)) * box.height;
}

/** A range symmetric about zero that covers every value of every series, and at least `±floor`. */
export function symmetricRange(series: number[][], floor: number): ValueRange {
  let extent = floor;
  for (const values of series) {
    for (const value of values) {
      extent = Math.max(extent, Math.abs(value));
    }
  }
  return { min: -extent, max: extent };
}

function rounded(value: number): number {
  return Math.round(value * 10) / 10;
}

/** An SVG path through each tick's value, slot centre to slot centre. */
export function linePath(values: number[], range: ValueRange, box: PlotBox): string {
  return values
    .map((value, tick) => {
      const command = tick === 0 ? "M" : "L";
      const x = rounded(tickX(tick, values.length, box));
      const y = rounded(valueY(value, range, box));
      return `${command}${x},${y}`;
    })
    .join(" ");
}

/** One bar per tick from zero to the tick's value, leaving a 2-unit gap between neighbours. */
export function zeroBars(values: number[], range: ValueRange, box: PlotBox): Bar[] {
  const slot = box.width / values.length;
  const zero = valueY(0, range, box);
  return values.map((value, tick) => {
    const y = valueY(value, range, box);
    return {
      tick,
      x: box.left + tick * slot + 1,
      y: Math.min(y, zero),
      width: Math.max(slot - 2, 1),
      height: Math.abs(zero - y),
    };
  });
}

/** The tick whose slot holds `x`, clamped to the plot. */
export function tickAtX(x: number, count: number, box: PlotBox): number {
  const tick = Math.floor(((x - box.left) / box.width) * count);
  return Math.min(count - 1, Math.max(0, tick));
}

/** The ticks the x axis labels: every 8 up to 64 ticks, every 16 beyond. */
export function axisTicks(count: number): number[] {
  const step = count <= 64 ? 8 : 16;
  const ticks: number[] = [];
  for (let tick = 0; tick < count; tick += step) {
    ticks.push(tick);
  }
  return ticks;
}
