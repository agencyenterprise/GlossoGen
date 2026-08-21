/**
 * Colours for chart series and heatmap cells.
 *
 * Slots are assigned in fixed order and never cycled: the first series always takes
 * slot 1, so removing a series from a filter does not repaint the ones that remain.
 * Past the last slot a series is left undrawn and counted, never merged: merging would
 * mean averaging aggregates computed over different numbers of runs, which is a
 * different number than the one the server answered with.
 *
 * The values live in `globals.css` as custom properties, so a chart drawn here
 * follows the theme without reading it. The light and dark steps are the same hues
 * re-stepped for their surface rather than a different palette, so a series keeps its
 * identity when the theme changes.
 *
 * The steps were checked for colour-vision separation against both surfaces. Do not
 * substitute them by eye.
 */

export const SERIES_SLOT_COUNT = 8;

/** Series colours beyond which a scatter's marks stop being pairwise separable. */
export const SCATTER_SERIES_LIMIT = 3;

const SERIES_VARIABLES = Array.from(
  { length: SERIES_SLOT_COUNT },
  (_, index) => `var(--series-${index + 1})`
);

/**
 * Return the colour for one series, by its position in the legend.
 *
 * Callers slice to `SERIES_SLOT_COUNT` before assigning, so an index past the last
 * slot means a caller stopped doing that. The neutral is what it gets: visibly not a
 * series colour, rather than a repeat of slot 1.
 */
export function seriesColor(index: number): string {
  const color = SERIES_VARIABLES[index];
  if (color === undefined) {
    return "var(--series-other)";
  }
  return color;
}

const RAMP_STEPS = 7;

export interface RampStep {
  /** The step's fill. */
  background: string;
  /** Text that clears WCAG contrast against that fill, in either theme. */
  color: string;
}

/**
 * Return a heatmap cell's fill and the text colour that stays readable on it.
 *
 * A range with no spread (one value, or every cell the same) takes the ramp's middle
 * step: stretching it to the extremes would draw a contrast that the data does not
 * carry.
 *
 * The ink is chosen per step per theme, because the ramp itself inverts between them:
 * step 1 is the palest blue on light and the darkest on dark, so the text that reads
 * on it flips too. Every pair was measured for contrast against its own step.
 */
export function rampStep(value: number, minimum: number, maximum: number): RampStep {
  if (maximum <= minimum) {
    return stepAt(Math.ceil(RAMP_STEPS / 2));
  }
  const position = (value - minimum) / (maximum - minimum);
  return stepAt(Math.min(RAMP_STEPS, Math.max(1, Math.ceil(position * RAMP_STEPS))));
}

function stepAt(step: number): RampStep {
  return { background: `var(--ramp-${step})`, color: `var(--ramp-${step}-ink)` };
}
