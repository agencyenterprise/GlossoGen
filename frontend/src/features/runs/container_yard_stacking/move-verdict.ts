/**
 * Formatting + verdict helpers for the container-yard `move_container` tool.
 *
 * Shared by the full verdict block (`yard-move-metadata-block.tsx`) and the
 * compact round-timeline summary (`plugin.tsx#summarizeToolVerdict`) so the
 * slot/verdict formatting lives in one place inside the scenario folder.
 */

import type { components } from "@/types/api.gen";

type ContainerYardMoveMetadata = components["schemas"]["ContainerYardMoveMetadata"];

/** "slot X → slot Y" for the move the batch plan expected at this step. */
export function formatExpectedMove(metadata: ContainerYardMoveMetadata): string {
  const from = metadata.expected_from_slot === null ? "?" : String(metadata.expected_from_slot);
  const to = metadata.expected_to_slot === null ? "?" : String(metadata.expected_to_slot);
  return `slot ${from} → slot ${to}`;
}

/** "slot X → slot Y" for the move the agent actually submitted. */
export function formatSubmittedMove(metadata: ContainerYardMoveMetadata): string {
  return `slot ${metadata.submitted_from_slot} → slot ${metadata.submitted_to_slot}`;
}

/** "slot X → slot Y" read from the raw `move_container` tool arguments. */
export function formatMoveArgs(args: Record<string, unknown>): string {
  const from = typeof args.from_slot === "number" ? args.from_slot : "?";
  const to = typeof args.to_slot === "number" ? args.to_slot : "?";
  return `slot ${from} → slot ${to}`;
}

/** Tri-state verdict: true (accepted), null (retryable soft-reject), false (rejected). */
export function moveVerdictAccepted(metadata: ContainerYardMoveMetadata): boolean | null {
  if (metadata.accepted) return true;
  if (metadata.soft_rejected) return null;
  return false;
}

/** Verdict label + text color for the full move-verdict block. */
export function moveVerdictLabel(metadata: ContainerYardMoveMetadata): {
  label: string;
  className: string;
} {
  if (metadata.accepted) {
    return { label: "accepted", className: "text-emerald-500" };
  }
  if (metadata.soft_rejected) {
    return { label: "soft-rejected (retryable)", className: "text-amber-500" };
  }
  return { label: "rejected (round failed)", className: "text-red-500" };
}
