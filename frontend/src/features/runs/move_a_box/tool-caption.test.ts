import { describe, expect, it } from "vitest";
import { moveABoxToolCaption } from "./tool-caption";

describe("moveABoxToolCaption", () => {
  it("captions a call with its reasoning argument", () => {
    const caption = moveABoxToolCaption({
      toolName: "act",
      toolArguments: {
        steps: [{ action: "drag", direction: "up" }],
        reasoning: "  Sending W as 87.  ",
      },
    });
    expect(caption).toEqual({ argumentName: "reasoning", text: "Sending W as 87." });
  });

  it("gives no caption when the reasoning is missing, blank or not text", () => {
    expect(moveABoxToolCaption({ toolName: "read_notifications", toolArguments: {} })).toBeNull();
    expect(
      moveABoxToolCaption({ toolName: "act", toolArguments: { reasoning: "   " } })
    ).toBeNull();
    expect(moveABoxToolCaption({ toolName: "act", toolArguments: { reasoning: 3 } })).toBeNull();
  });
});
