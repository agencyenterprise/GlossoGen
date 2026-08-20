"use client";

/**
 * The pieces every chart here shares: a tooltip, a legend, and the axis styling.
 *
 * The tooltip carries the observation count beside the value, because an aggregate
 * over three runs and one over ninety look identical on the mark. A value the query
 * could not compute shows as "no observations" rather than as zero.
 *
 * Text never wears a series colour: the swatch beside a label carries identity and
 * the text stays in the theme's ink, which stays legible on both surfaces.
 */

import type { ChartSeries } from "../chart-series";
import { COUNT_FIELD_PREFIX } from "../chart-series";

export const AXIS_TICK = { fill: "var(--color-muted-foreground)", fontSize: 11 };

export const GRID_STROKE = "var(--color-border)";

/**
 * Fixed to one locale on purpose.
 *
 * The viewer's locale would render 0.5 as "0,5" in much of Europe, which reads as a
 * thousands separator to everyone else and disagrees with the CSV this chart
 * downloads and with what `glossogen analyze` prints. A number that means different
 * things to two readers of the same dashboard is worse than one that is not in their
 * local convention.
 */
const NUMBER_FORMAT = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 4 });

const INTEGER_FORMAT = new Intl.NumberFormat("en-US");

export function formatValue(value: number | null): string {
  if (value === null) {
    return "no observations";
  }
  if (Number.isInteger(value)) {
    return INTEGER_FORMAT.format(value);
  }
  return NUMBER_FORMAT.format(value);
}

/**
 * The one field this tooltip reads off what Recharts hands it: the row the mark came
 * from. Every value and count is on that row already, so nothing here has to agree
 * with the rest of the library's payload shape.
 */
interface TooltipEntry {
  payload?: Record<string, unknown>;
}

/** One row of a tooltip: a swatch, a label, the value, and what it was computed over. */
export function TooltipRow({
  color,
  label,
  value,
  observations,
}: {
  color: string;
  label: string;
  value: number | null;
  observations: number | null;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span
        aria-hidden
        className="mt-1 h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="text-muted-foreground">{label}</span>
      <span className="ml-auto font-medium tabular-nums">{formatValue(value)}</span>
      {observations === null ? null : (
        <span className="text-[11px] text-muted-foreground tabular-nums">n={observations}</span>
      )}
    </div>
  );
}

export function TooltipShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-44 rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1.5 font-medium text-popover-foreground">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

/** The tooltip bar, line, and area charts share. */
export function SeriesTooltip({
  active,
  label,
  payload,
  series,
}: {
  active?: boolean;
  label?: string | number;
  payload?: readonly TooltipEntry[];
  series: ChartSeries[];
}) {
  if (!active || payload === undefined || payload.length === 0) {
    return null;
  }
  const row = payload[0]?.payload ?? {};
  return (
    <TooltipShell title={String(label ?? "")}>
      {series.map(entry => {
        const value = row[entry.key];
        const observations = row[`${COUNT_FIELD_PREFIX}${entry.key}`];
        return (
          <TooltipRow
            key={entry.key}
            color={entry.color}
            label={entry.name}
            value={typeof value === "number" ? value : null}
            observations={typeof observations === "number" ? observations : null}
          />
        );
      })}
    </TooltipShell>
  );
}

/** The legend every chart with two or more series carries. */
export function ChartLegend({ series }: { series: ChartSeries[] }) {
  if (series.length < 2) {
    return null;
  }
  return (
    <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {series.map(entry => (
        <li key={entry.key} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          {entry.name}
        </li>
      ))}
    </ul>
  );
}

/** Said when a query answered, but with nothing to draw. */
export function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-border">
      <p className="max-w-sm text-center text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
