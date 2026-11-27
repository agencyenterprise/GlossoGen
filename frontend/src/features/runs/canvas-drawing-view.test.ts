// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CanvasDrawingView } from "./canvas-drawing-view";
import { mergeEntries } from "./display-entry";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const DRAWING = {
  width: 4,
  height: 3,
  pixels: [
    { x: 0, y: 0 },
    { x: 3, y: 2 },
  ],
};

it("paints one black square per pixel at the pixel's column and row", async () => {
  await act(async () => root.render(createElement(CanvasDrawingView, { drawing: DRAWING })));

  const painted = [...container.querySelectorAll('rect[fill="#000000"]')].map(rect => [
    rect.getAttribute("x"),
    rect.getAttribute("y"),
  ]);
  expect(painted).toEqual([
    ["0", "0"],
    ["3", "2"],
  ]);
  expect(container.querySelector("svg")?.getAttribute("viewBox")).toBe("0 0 4 3");
  expect(container.textContent).toContain("2 pixels · 4x3 canvas");
});

it("carries a drawing message's pixels into its chat entry", () => {
  const entries = mergeEntries(
    [
      {
        message_id: "m1",
        channel_id: "link_a",
        sender_agent_id: "viewer_a_1",
        sender_display_name: "Viewer 1",
        text: "",
        timestamp: "2026-11-27T10:00:00.000Z",
        round_number: 1,
        token_count: 0,
        drawing: DRAWING,
      },
    ],
    [],
    [],
    [],
    [],
    {},
    {},
    {},
    {}
  );

  expect(entries.map(entry => entry.drawing)).toEqual([DRAWING]);
});
