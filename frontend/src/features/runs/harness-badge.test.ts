import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { deriveAgentInstances } from "./agent-instance";
import { harnessLabel, seatDescription } from "./harness-badge";

/**
 * A seat's harness, as the run viewer shows it. Runs recorded under the default
 * harness must read as they always have, so only other harnesses are named.
 */

type AgentDetail = components["schemas"]["AgentDetail"];
type AgentSwapEventDTO = components["schemas"]["AgentSwapEventDTO"];

describe("seatDescription", () => {
  it("is provider/model alone under the default harness", () => {
    expect(
      seatDescription({ provider: "anthropic", model: "claude-sonnet-4-6", harness: "pydantic-ai" })
    ).toBe("anthropic/claude-sonnet-4-6");
  });

  it("names a shipped CLI harness by the CLI it runs", () => {
    expect(seatDescription({ provider: "openai", model: "gpt-5.4", harness: "codex" })).toBe(
      "openai/gpt-5.4 · Codex"
    );
    expect(harnessLabel("claude-agent-sdk")).toBe("Claude Code");
  });

  it("shows a harness from another package under its own name", () => {
    expect(harnessLabel("my-harness")).toBe("my-harness");
  });
});

describe("deriveAgentInstances", () => {
  it("gives a swapped-in generation the harness its swap brought in", () => {
    const agent = {
      agent_id: "field_observer",
      role_name: "Field Observer",
      model: "claude-sonnet-4-6",
      provider: "anthropic",
      harness: "claude-agent-sdk",
      system_prompt: "",
      channel_ids: [],
      tool_names: [],
    } as unknown as AgentDetail;
    const swap = {
      agent_id: "field_observer",
      round_number: 3,
      timestamp: "2026-10-12T00:00:00Z",
      new_model: "claude-sonnet-4-6",
      new_provider: "anthropic",
      new_harness: "pydantic-ai",
      system_prompt: "",
    } as AgentSwapEventDTO;

    const instances = deriveAgentInstances([agent], [swap], 5, false);

    expect(instances.map(instance => instance.harness)).toEqual([
      "claude-agent-sdk",
      "pydantic-ai",
    ]);
  });
});
