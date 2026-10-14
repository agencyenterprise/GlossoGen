/**
 * dead_drop's `scenario_extras` payload, and the type guard that narrows the
 * plug-in boundary's `unknown` to it.
 */

import type { components } from "@/types/api.gen";

export type DeadDropRunExtras = components["schemas"]["DeadDropRunExtras"];
export type DeadDropRoundFiles = components["schemas"]["DeadDropRoundFiles"];
export type DeadDropFile = components["schemas"]["DeadDropFile"];
export type DeadDropFsEffect = components["schemas"]["DeadDropFsEffect"];

export function isDeadDropExtras(extras: unknown): extras is DeadDropRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "dead_drop";
}
