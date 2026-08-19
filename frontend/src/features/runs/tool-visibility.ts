import { useCallback, useMemo, useState } from "react";
import type { DisplayEntry } from "./display-entry";

/** Strip the MCP prefix tool names carry over the wire. */
export function cleanToolName(name: string): string {
  return name.replace(/^mcp__comms__/, "");
}

/**
 * The platform's own communication tools, hidden by default.
 *
 * Their calls restate what the transcript already shows: a ``send_message``
 * call is the chat bubble next to it, and the three read tools return the
 * messages, channels and rosters the viewer is looking at. They stay one click
 * away because the arguments are the pristine pre-noise text, which is the
 * thing to look at when a run corrupts what agents receive.
 *
 * Every other tool is a scenario's own, so it is shown by default: it carries
 * the actions the run is about.
 */
const PLATFORM_COMMUNICATION_TOOLS = new Set([
  "send_message",
  "read_notifications",
  "read_channel",
  "list_channels",
  "get_channel_members",
]);

/** Whether a tool renders unless the viewer says otherwise. */
export function isScenarioTool(toolName: string): boolean {
  return !PLATFORM_COMMUNICATION_TOOLS.has(toolName);
}

export interface ToolVisibility {
  /** Every tool called in the run, scenario tools first, alphabetical within each group. */
  toolNames: string[];
  visibleCount: number;
  isVisible: (toolName: string) => boolean;
  toggle: (toolName: string) => void;
  setAll: (visible: boolean) => void;
}

function collectToolNames(entries: DisplayEntry[]): string[] {
  const names = new Set<string>();
  for (const entry of entries) {
    if (entry.is_tool_use || entry.is_notification_result) {
      names.add(cleanToolName(entry.tool_name));
    }
  }
  const scenario = [...names].filter(isScenarioTool).sort();
  const platform = [...names].filter(name => !isScenarioTool(name)).sort();
  return [...scenario, ...platform];
}

/**
 * Per-tool chat visibility, defaulting to a scenario's own tools on and the
 * platform's communication tools off.
 *
 * State is the viewer's explicit choices rather than the resolved set, so a
 * tool first called late in a live run still arrives at its own default
 * instead of inheriting whatever the set held when the run started.
 */
export function useToolVisibility(entries: DisplayEntry[]): ToolVisibility {
  const [choices, setChoices] = useState<Map<string, boolean>>(new Map());
  const toolNames = useMemo(() => collectToolNames(entries), [entries]);

  const isVisible = useCallback(
    (toolName: string) => {
      const choice = choices.get(toolName);
      if (choice === undefined) {
        return isScenarioTool(toolName);
      }
      return choice;
    },
    [choices]
  );

  const toggle = useCallback((toolName: string) => {
    setChoices(previous => {
      const next = new Map(previous);
      const choice = next.get(toolName);
      if (choice === undefined) {
        next.set(toolName, !isScenarioTool(toolName));
      } else {
        next.set(toolName, !choice);
      }
      return next;
    });
  }, []);

  const setAll = useCallback(
    (visible: boolean) => {
      setChoices(new Map(toolNames.map(name => [name, visible])));
    },
    [toolNames]
  );

  const visibleCount = toolNames.filter(isVisible).length;

  return { toolNames, visibleCount, isVisible, toggle, setAll };
}
