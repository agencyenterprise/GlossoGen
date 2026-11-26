/**
 * The caption that move_a_box shows under each collapsed tool-call row: the
 * operator's `reasoning` argument, which every move_a_box tool takes.
 */

import type { ToolCaption } from "../scenario-plugin";

const REASONING_ARGUMENT = "reasoning";

/** The call's `reasoning` argument as a caption, or null when the call has none. */
export function moveABoxToolCaption({
  toolArguments,
}: {
  toolName: string;
  toolArguments: Record<string, unknown>;
}): ToolCaption | null {
  const reasoning = toolArguments[REASONING_ARGUMENT];
  if (typeof reasoning !== "string") {
    return null;
  }
  const text = reasoning.trim();
  if (text === "") {
    return null;
  }
  return { argumentName: REASONING_ARGUMENT, text };
}
