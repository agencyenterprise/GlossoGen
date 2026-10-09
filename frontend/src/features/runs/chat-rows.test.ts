import { describe, expect, it } from "vitest";
import { buildChatRows } from "./chat-rows";
import { mergeEntries } from "./display-entry";

function messages(count: number) {
  return mergeEntries(
    [],
    [],
    [],
    Array.from({ length: count }, (_, cycle) => ({
      message_id: `failure-${cycle}`,
      agent_id: "member_1",
      timestamp: new Date(1_700_000_000_000 + cycle).toISOString(),
      round_number: 12,
      cycle,
      error_type: "RateLimitError",
      message: "Provider limit reached",
    })),
    {},
    {},
    {}
  );
}

describe("chat navigation rows", () => {
  it("keeps a 5,000-entry single-agent round individually virtualizable", () => {
    const entries = messages(5000);
    const { rows, rowIndexByMessage, rowIndexByRound } = buildChatRows(entries);
    expect(rows).toHaveLength(5002);
    expect(rows[0]!.kind).toBe("round-start");
    expect(rows.at(-1)?.kind).toBe("round-end");
    expect(rowIndexByRound.get(12)).toBe(0);
    for (const entry of entries) {
      const index = rowIndexByMessage.get(entry.message_id)!;
      const row = rows[index]!;
      expect(row.kind).toBe("entry");
      if (row.kind === "entry") expect(row.entry).toBe(entry);
    }
    expect(new Set(rows.map(row => row.key)).size).toBe(rows.length);
  });

  it("preserves turns, historical display names and round jump targets", () => {
    const entries = messages(4);
    entries[1]!.sender_display_name = "Alice (generation 2)";
    entries[2]!.sender_agent_id = "member_2";
    entries[3]!.round_number = 13;
    const { rows, rowIndexByRound } = buildChatRows(entries);
    const activity = rows.filter(row => row.kind === "entry");
    expect(activity.map(row => row.turn.index)).toEqual([0, 0, 1, 0]);
    expect(activity.map(row => row.isTurnStart)).toEqual([true, false, true, true]);
    expect(activity[0]!.turn.displayName).toBe("Alice (generation 2)");
    expect(rows[rowIndexByRound.get(13)!]).toMatchObject({ kind: "round-start", roundNumber: 13 });
  });

  it("keeps surviving entry keys stable after filters and live appends", () => {
    const entries = messages(10);
    const original = buildChatRows(entries).rows.filter(row => row.kind === "entry");
    const filtered = buildChatRows(entries.slice(3)).rows.filter(row => row.kind === "entry");
    const appended = buildChatRows(messages(11)).rows.filter(row => row.kind === "entry");
    expect(filtered.map(row => row.key)).toEqual(original.slice(3).map(row => row.key));
    expect(appended.slice(0, 10).map(row => row.key)).toEqual(original.map(row => row.key));
    expect(buildChatRows([]).rows).toEqual([]);
  });
});
