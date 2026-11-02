/**
 * What signal_game's round-detail panel needs to know about items and actions.
 *
 * An item is a colour, a colour and a shape, or a fill, a colour and a shape. The colours are the scenario's own
 * palette names, drawn here in hues that read on both the light and the dark
 * surface. The action log merges both players' moves into the round's single
 * numbering, which is the order the players saw them in.
 */

import type { components } from "@/types/api.gen";

type SignalGameItem = components["schemas"]["SignalGameItem"];
type SignalGamePlayerSide = components["schemas"]["SignalGamePlayerSide"];
type SignalGameCell = components["schemas"]["SignalGameCell"];

/** Fill for each palette colour. A name the panel does not know is drawn grey. */
export const ITEM_COLORS: Record<string, string> = {
  red: "#dc2626",
  blue: "#2563eb",
  green: "#16a34a",
  yellow: "#eab308",
  purple: "#9333ea",
  orange: "#ea580c",
};

const UNKNOWN_COLOR = "#6b7280";

export function itemColor(colour: string): string {
  return ITEM_COLORS[colour] ?? UNKNOWN_COLOR;
}

/** The item as the players read it: ``red``, ``red circle`` or ``striped red circle``. */
export function itemLabel(item: SignalGameItem): string {
  const words: string[] = [];
  if (item.fill !== null) words.push(item.fill);
  words.push(item.colour);
  if (item.shape !== null) words.push(item.shape);
  return words.join(" ");
}

export function sameItem(first: SignalGameItem, second: SignalGameItem): boolean {
  return (
    first.colour === second.colour && first.shape === second.shape && first.fill === second.fill
  );
}

export function cellLabel(cell: SignalGameCell): string {
  return `r${cell.row}c${cell.col}`;
}

/** The short name for a player, ``A`` for ``player_a``. */
export function playerLetter(agentId: string): string {
  const parts = agentId.split("_");
  const last = parts[parts.length - 1];
  if (last === undefined || last.length === 0) return agentId;
  return last.toUpperCase();
}

/** One line of the action log: one player's consecutive steps that carry the same
 *  reasoning, or that player's ``end_round``. A ``move`` call logs its reasoning on every
 *  step, so a line is usually one call. Two back-to-back calls with the same reasoning
 *  (or with ``move_reasoning`` off, where every reasoning is null) share a line: the
 *  events carry no call id to tell them apart. */
export interface ActionGroup {
  agentId: string;
  firstSequence: number;
  lastSequence: number;
  kind: "move" | "end";
  directions: string[];
  /** Where the last step of the group, or the finish, left the player. */
  cell: SignalGameCell;
  reasoning: string | null;
}

interface FlatAction {
  agentId: string;
  sequence: number;
  kind: "move" | "end";
  direction: string;
  cell: SignalGameCell;
  reasoning: string | null;
}

/** Both players' actions in the round's numbering, one player's consecutive steps with
 *  the same reasoning merged into one line. */
export function actionLog(players: SignalGamePlayerSide[]): ActionGroup[] {
  const flat: FlatAction[] = [];
  for (const side of players) {
    for (const step of side.steps) {
      flat.push({
        agentId: side.agent_id,
        sequence: step.sequence,
        kind: "move",
        direction: step.direction,
        cell: step.cell,
        reasoning: step.reasoning,
      });
    }
    if (side.end_sequence !== null) {
      flat.push({
        agentId: side.agent_id,
        sequence: side.end_sequence,
        kind: "end",
        direction: "end_round",
        cell: side.final_cell,
        reasoning: side.end_reasoning,
      });
    }
  }
  flat.sort((first, second) => first.sequence - second.sequence);

  const groups: ActionGroup[] = [];
  for (const action of flat) {
    const previous = groups[groups.length - 1];
    const continues =
      previous !== undefined &&
      action.kind === "move" &&
      previous.kind === "move" &&
      previous.agentId === action.agentId &&
      previous.lastSequence + 1 === action.sequence &&
      previous.reasoning === action.reasoning;
    if (continues) {
      previous.lastSequence = action.sequence;
      previous.directions.push(action.direction);
      previous.cell = action.cell;
      continue;
    }
    groups.push({
      agentId: action.agentId,
      firstSequence: action.sequence,
      lastSequence: action.sequence,
      kind: action.kind,
      directions: [action.direction],
      cell: action.cell,
      reasoning: action.reasoning,
    });
  }
  return groups;
}
