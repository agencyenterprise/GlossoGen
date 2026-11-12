// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { mergeEntries } from "./display-entry";
import { RoundTimelineModal } from "./round-timeline-modal";

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

function linkMessage() {
  return {
    message_id: "m1",
    channel_id: "link",
    sender_agent_id: "member_1",
    sender_display_name: "Member 1",
    text: "a message on the link",
    timestamp: "2026-10-09T06:14:00.000Z",
    round_number: 1,
    token_count: 4,
  };
}

function unrecognizedEvent() {
  return {
    event_id: "gone-1",
    event_type: "gone_board_dealt",
    round_number: 1,
    timestamp: "2026-10-09T06:14:01.000Z",
    payload: { event_type: "gone_board_dealt", board: [1] },
  };
}

it("lists a link message and leaves an unrecognized event out of the round's timeline", async () => {
  const entries = mergeEntries([linkMessage()], [], [], [], [unrecognizedEvent()], {}, {}, {}).map(
    entry => {
      // An unrecognized entry has no channel of its own. Giving it the primary
      // channel makes the filter the only thing keeping it out of the timeline.
      if (entry.is_unrecognized) return { ...entry, channel_id: "link", text: "unrecognized row" };
      return entry;
    }
  );
  expect(entries.some(entry => entry.is_unrecognized)).toBe(true);

  await act(async () => {
    root.render(
      createElement(RoundTimelineModal, {
        roundNumber: 1,
        messages: entries,
        scenarioName: "veyru",
        primaryChannelIds: ["link"],
        scenarioExtras: null,
        roundEnding: null,
        roundResults: [],
        onClose: () => {},
      })
    );
  });

  const shown = document.body.textContent ?? "";
  expect(shown).toContain("a message on the link");
  expect(shown).not.toContain("unrecognized row");
});
