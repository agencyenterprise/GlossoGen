import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { DEFAULT_SCENARIO_PLUGIN } from "./default-plugin";
import { mergeEntries, notificationDisplaysByCallId } from "./display-entry";
import type { ScenarioPlugin } from "./scenario-plugin";

type ToolUseEntry = components["schemas"]["ToolUseEntry"];

const WAKE_RESULT = JSON.stringify({
  type: "wake",
  wake_reasons: ["new_notification"],
  round: 1,
  waited_seconds: 0,
  workspace: "Woke: new_notification.\nDepot now (v0): r1=8",
  lifecycle: [],
});

function readNotifications(callId: string, result: string): ToolUseEntry {
  return {
    message_id: `tool-${callId}`,
    sender_agent_id: "crafter_1",
    timestamp: "2026-10-09T06:14:00.000Z",
    round_number: 1,
    tool_name: "read_notifications",
    arguments: {},
    result,
    call_id: callId,
    result_timestamp: "2026-10-09T06:14:01.000Z",
    result_round_number: 1,
  };
}

describe("a read_notifications result a scenario rendered itself", () => {
  it("is split from its call and paired by call_id whatever its type", () => {
    const entries = mergeEntries([], [], [readNotifications("c1", WAKE_RESULT)], [], {}, {}, {});
    const call = entries.find(e => e.is_tool_use);
    const result = entries.find(e => e.is_notification_result);
    expect(call?.paired_message_id).toBe(result?.message_id);
    expect(result?.paired_message_id).toBe(call?.message_id);
    expect(result?.call_id).toBe("c1");
    expect(result?.notification_display).toBeNull();
  });

  it("carries the plug-in's rendering when the plug-in renders it", () => {
    const plugin: ScenarioPlugin = {
      ...DEFAULT_SCENARIO_PLUGIN,
      renderNotification: ({ payload }) => (payload.type === "wake" ? "rendered wake" : null),
    };
    const toolUse = [
      readNotifications("c1", WAKE_RESULT),
      readNotifications("c2", JSON.stringify({ type: "no_activity", detail: "No new messages." })),
      readNotifications("c3", "not json"),
    ];
    const displays = notificationDisplaysByCallId(toolUse, plugin);
    expect(displays).toEqual({ c1: "rendered wake" });
    const entries = mergeEntries([], [], toolUse, [], {}, {}, displays);
    const rendered = entries.find(e => e.is_notification_result && e.call_id === "c1");
    expect(rendered?.notification_display).toBe("rendered wake");
    expect(entries.some(e => e.is_notification_result && e.call_id === "c3")).toBe(false);
  });
});
