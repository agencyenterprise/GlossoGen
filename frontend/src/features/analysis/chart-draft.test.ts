import { describe, expect, it } from "vitest";
import { clampEncoding, newChart } from "./chart-draft";
import type { ChartEncoding } from "./use-dashboards";

/**
 * What a chart's encoding is allowed to say.
 *
 * Both of these were shipped broken and neither `tsc` nor any other check could have
 * said so: an index pointing past the measures is a valid `number`, and an optional
 * field's absence type-checks. The backend refuses both, so the failure shows up as a
 * 422 on save or as a silently discarded setting.
 */

const MEASURES = [
  {
    source: "metric",
    key: "round_success",
    label: "Round success",
    score_unit: "",
    rows_with_value: 3,
  },
];

describe("newChart", () => {
  it("points both axes at a measure the chart actually has", () => {
    const chart = newChart("chart-1", MEASURES);

    expect(chart.query.measures).toHaveLength(1);
    expect(chart.encoding.measure_index).toBe(0);
    // Not 1: a fresh chart has one measure, and the stored spec refuses an index past
    // the list. The default kind is bar, which never reads this, so the refusal only
    // appeared on save.
    expect(chart.encoding.y_measure_index).toBe(0);
    expect(chart.encoding.error_measure_index).toBeNull();
  });

  it("starts with no error bars", () => {
    expect(newChart("chart-1", MEASURES).encoding.error_measure_index).toBeNull();
  });
});

describe("clampEncoding", () => {
  const encoding = (patch: Partial<ChartEncoding>): ChartEncoding => ({
    measure_index: 0,
    y_measure_index: 0,
    error_measure_index: null,
    ...patch,
  });

  it("keeps an error measure that is still drawable", () => {
    const clamped = clampEncoding(
      encoding({ measure_index: 0, y_measure_index: 1, error_measure_index: 2 }),
      3
    );

    expect(clamped.error_measure_index).toBe(2);
  });

  it("keeps the error measure when an earlier measure is removed", () => {
    // Three measures, error bars on the last, then the first is deleted. The setting
    // was silently dropped because rebuilding the object without the optional field
    // type-checks.
    const clamped = clampEncoding(
      encoding({ measure_index: 0, y_measure_index: 0, error_measure_index: 2 }),
      2
    );

    expect(clamped.error_measure_index).toBe(1);
  });

  it("drops the error measure when only one measure is left", () => {
    const clamped = clampEncoding(encoding({ error_measure_index: 1 }), 1);

    expect(clamped.error_measure_index).toBeNull();
  });

  it("drops the error measure when it would sit on the measure it annotates", () => {
    const clamped = clampEncoding(
      encoding({ measure_index: 1, y_measure_index: 0, error_measure_index: 1 }),
      2
    );

    expect(clamped.error_measure_index).toBeNull();
  });

  it("pulls every index back inside the list", () => {
    const clamped = clampEncoding(
      encoding({ measure_index: 5, y_measure_index: 4, error_measure_index: 9 }),
      2
    );

    expect(clamped.measure_index).toBe(1);
    expect(clamped.y_measure_index).toBe(1);
    // Would land on measure_index, which removes it from the chart.
    expect(clamped.error_measure_index).toBeNull();
  });
});
