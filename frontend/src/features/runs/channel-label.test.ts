import { describe, expect, it } from "vitest";
import { channelLabel, channelTag } from "./channel-label";

const ROLE_NAMES = new Map([
  ["viewer_a_1", "Viewer 1 (Team A)"],
  ["viewer_a_2", "Viewer 2 (Team A)"],
  ["viewer_a_3", "Viewer 3 (Team A)"],
  ["crafter_1", "Crafter 1"],
  ["crafter_2", "Crafter 2"],
]);

function roleNameOf(agentId: string): string {
  return ROLE_NAMES.get(agentId) ?? agentId;
}

describe("channelLabel", () => {
  it("names a direct channel after its members, with their shared team once", () => {
    expect(channelLabel("dm:viewer_a_1+viewer_a_2", roleNameOf)).toBe(
      "Viewer 1 ↔ Viewer 2 (Team A)"
    );
  });

  it("lists three or more members with commas", () => {
    expect(channelLabel("dm:viewer_a_1+viewer_a_2+viewer_a_3", roleNameOf)).toBe(
      "Viewer 1, Viewer 2, Viewer 3 (Team A)"
    );
  });

  it("keeps role names whole when they share no suffix", () => {
    expect(channelLabel("dm:crafter_1+crafter_2", roleNameOf)).toBe("Crafter 1 ↔ Crafter 2");
    expect(channelLabel("dm:crafter_1+viewer_a_1", roleNameOf)).toBe(
      "Crafter 1 ↔ Viewer 1 (Team A)"
    );
  });

  it("falls back to the agent id for a member the run does not list", () => {
    expect(channelLabel("dm:viewer_a_1+viewer_z_9", roleNameOf)).toBe(
      "Viewer 1 (Team A) ↔ viewer_z_9"
    );
  });

  it("humanizes any other channel's id", () => {
    expect(channelLabel("link_a", roleNameOf)).toBe("Link A");
  });
});

describe("channelTag", () => {
  it("names a direct channel after its members", () => {
    expect(channelTag("dm:viewer_a_1+viewer_a_2", roleNameOf)).toBe("Viewer 1 ↔ Viewer 2 (Team A)");
  });

  it("keeps any other channel's id", () => {
    expect(channelTag("link_a", roleNameOf)).toBe("link_a");
  });
});
