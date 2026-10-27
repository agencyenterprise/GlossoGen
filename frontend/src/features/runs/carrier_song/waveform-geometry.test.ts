import { describe, expect, it } from "vitest";
import {
  axisTicks,
  linePath,
  symmetricRange,
  tickAtX,
  tickX,
  valueAt,
  valueY,
  zeroBars,
  type PlotBox,
} from "./waveform-geometry";

const BOX: PlotBox = { left: 10, top: 0, width: 40, height: 20 };

describe("waveform geometry", () => {
  it("puts each tick at the centre of its slot", () => {
    expect(tickX(0, 4, BOX)).toBe(15);
    expect(tickX(3, 4, BOX)).toBe(45);
  });

  it("maps the range's max to the top and its min to the bottom", () => {
    const range = { min: -2, max: 2 };
    expect(valueY(2, range, BOX)).toBe(0);
    expect(valueY(0, range, BOX)).toBe(10);
    expect(valueY(-2, range, BOX)).toBe(20);
  });

  it("covers every series symmetrically, and at least the floor", () => {
    expect(symmetricRange([[1, -3], [2]], 1)).toEqual({ min: -3, max: 3 });
    expect(symmetricRange([[0, 0]], 1)).toEqual({ min: -1, max: 1 });
  });

  it("draws a line through every tick", () => {
    expect(linePath([2, -2], { min: -2, max: 2 }, BOX)).toBe("M20,0 L40,20");
  });

  it("draws bars from zero, up for positive values and down for negative ones", () => {
    const [up, down, flat] = zeroBars([2, -1, 0], { min: -2, max: 2 }, BOX);
    expect(up).toMatchObject({ tick: 0, y: 0, height: 10 });
    expect(down).toMatchObject({ tick: 1, y: 10, height: 5 });
    expect(flat).toMatchObject({ tick: 2, height: 0 });
  });

  it("finds the tick under a point and clamps outside the plot", () => {
    expect(tickAtX(29, 4, BOX)).toBe(1);
    expect(tickAtX(0, 4, BOX)).toBe(0);
    expect(tickAtX(99, 4, BOX)).toBe(3);
  });

  it("reads a tick's value and refuses one outside the series", () => {
    expect(valueAt([4, 5], 1)).toBe(5);
    expect(() => valueAt([4, 5], 2)).toThrow(RangeError);
  });

  it("labels every 8 ticks up to 64 and every 16 beyond", () => {
    expect(axisTicks(64)).toEqual([0, 8, 16, 24, 32, 40, 48, 56]);
    expect(axisTicks(96)).toEqual([0, 16, 32, 48, 64, 80]);
  });
});
