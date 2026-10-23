import { describe, expect, it } from "vitest";
import { formatModelSettings } from "./format";

describe("formatModelSettings", () => {
  it("lists every setting the agent was sent", () => {
    expect(formatModelSettings({ max_tokens: 2048, thinking: "high" })).toBe(
      "max_tokens 2048 · thinking high"
    );
  });

  it("leaves out a setting the agent was not sent", () => {
    expect(formatModelSettings({ max_tokens: 16384, thinking: null })).toBe("max_tokens 16384");
    expect(formatModelSettings({ max_tokens: 16384 })).toBe("max_tokens 16384");
  });

  it("writes lists and objects as JSON", () => {
    expect(
      formatModelSettings({
        max_tokens: 1,
        stop_sequences: ["END"],
        extra_body: { reasoning: { exclude: true } },
      })
    ).toBe('max_tokens 1 · stop_sequences ["END"] · extra_body {"reasoning":{"exclude":true}}');
  });

  it("shows a thinking switch as true or false", () => {
    expect(formatModelSettings({ max_tokens: 1, thinking: false })).toBe(
      "max_tokens 1 · thinking false"
    );
  });
});
