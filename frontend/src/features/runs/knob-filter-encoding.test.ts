/**
 * The knob-condition encoding, which has a second implementation in Python.
 *
 * `parseKnobFilter` mirrors `_find_separator` and `parse_knob_filter` in
 * `glossogen/knob_filter.py`. Nothing makes the two agree except these tests
 * and the ones in `tests/unit/test_knob_filter.py`, so the cases below are the
 * same cases that file pins, in the same order, and a change to one side that
 * is not made to the other should fail here.
 */

import { describe, expect, it } from "vitest";

import { describeKnobFilter, parseKnobFilter } from "./knob-filter-encoding";

describe("parseKnobFilter", () => {
  it.each([
    ["round_count=15", "round_count", "=", "15"],
    ["round_count!=15", "round_count", "!=", "15"],
    ["round_count>=15", "round_count", ">=", "15"],
    ["round_count<=15", "round_count", "<=", "15"],
    ["round_count>15", "round_count", ">", "15"],
    ["round_count<15", "round_count", "<", "15"],
  ])("reads %s", (raw, knob, operator, value) => {
    expect(parseKnobFilter(raw)).toEqual({ knob, operator, value });
  });

  it("trims the whitespace around each part, as the Python parser does", () => {
    expect(parseKnobFilter("  round_count  >=  15  ")).toEqual({
      knob: "round_count",
      operator: ">=",
      value: "15",
    });
  });

  it("allows an empty value, which asks for the empty string", () => {
    expect(parseKnobFilter("judge_model=")).toEqual({
      knob: "judge_model",
      operator: "=",
      value: "",
    });
  });

  // The knob name ends at the first operator, so a value may carry one. Taking
  // the longest operator anywhere would split "judge_model=gpt>=5" on ">=".
  it.each([
    ["judge_model=gpt>=5", "judge_model", "gpt>=5"],
    ["judge_model=a!=b", "judge_model", "a!=b"],
    ["judge_model=x<y", "judge_model", "x<y"],
  ])("ends the knob name at the first operator in %s", (raw, knob, value) => {
    const parsed = parseKnobFilter(raw);
    expect(parsed).not.toBeNull();
    expect(parsed?.knob).toBe(knob);
    expect(parsed?.operator).toBe("=");
    expect(parsed?.value).toBe(value);
  });

  // An operator at index 0 leaves an empty knob name. Skipping it and taking the
  // next one would read ">=200" as a knob named ">", which parses and matches
  // nothing; Python raises KnobFilterParseError for the same strings.
  it.each([">=200", "=15", "<5"])("refuses %s, which names no knob", raw => {
    expect(parseKnobFilter(raw)).toBeNull();
  });

  // The operator is at index 2 here, so an index-0 guard would accept this with
  // an empty knob name. Python refuses it, because it checks the trimmed name.
  it.each(["  =15  ", "  >=200", "\t!=x"])("refuses %s, whitespace and all", raw => {
    expect(parseKnobFilter(raw)).toBeNull();
  });

  it.each(["roundcount15", "nonsense", ""])("refuses %s, which has no operator", raw => {
    expect(parseKnobFilter(raw)).toBeNull();
  });

  it("prefers the longest operator starting at the same index", () => {
    expect(parseKnobFilter("k>=1")?.operator).toBe(">=");
    expect(parseKnobFilter("k<=1")?.operator).toBe("<=");
    expect(parseKnobFilter("k!=1")?.operator).toBe("!=");
  });

  it("reads the null token as an ordinary value, leaving the meaning to the server", () => {
    expect(parseKnobFilter("swap_round=null")).toEqual({
      knob: "swap_round",
      operator: "=",
      value: "null",
    });
  });
});

describe("describeKnobFilter", () => {
  it("spaces the parts out for a reader", () => {
    expect(describeKnobFilter("round_time_budget_seconds>=200")).toBe(
      "round_time_budget_seconds >= 200"
    );
  });

  it("falls back to the raw string when there is nothing to split", () => {
    expect(describeKnobFilter("nonsense")).toBe("nonsense");
  });
});
