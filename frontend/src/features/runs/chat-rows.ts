import type { DisplayEntry } from "./display-entry";

interface Turn {
  agentId: string;
  timestamp: string;
  index: number;
  displayName?: string;
}

export type ChatRow =
  | { kind: "round-start" | "round-end" | "closing"; key: string; roundNumber: number }
  | {
      kind: "entry";
      key: string;
      roundNumber: number;
      turn: Turn;
      isTurnStart: boolean;
      entry: DisplayEntry;
    };

/** Build measured rows and navigation indexes in one pass. Entries share only
 * their turn's header metadata; no intermediate round/turn entry arrays.
 *
 * `announcedRounds` (ascending) are rounds that get a section even when none of
 * their entries survive the filters, because the run recorded a briefing or an
 * ending for them. Entries are expected in ascending round order. */
export function buildChatRows(messages: DisplayEntry[], announcedRounds: number[]) {
  const rows: ChatRow[] = [];
  const rowIndexByRound = new Map<number, number>();
  const rowIndexByMessage = new Map<string, number>();
  let currentRound: number | undefined;
  let turn: Turn | undefined;
  let nextAnnounced = 0;

  function addBoundary(kind: "round-start" | "round-end", roundNumber: number) {
    rows.push({ kind, key: `${kind}-${roundNumber}`, roundNumber });
  }

  function openRound(roundNumber: number) {
    if (currentRound !== undefined) addBoundary("round-end", currentRound);
    rowIndexByRound.set(roundNumber, rows.length);
    addBoundary("round-start", roundNumber);
    currentRound = roundNumber;
    turn = undefined;
  }

  /** Open every announced round below `limit` that has not been opened yet. */
  function openAnnouncedBelow(limit: number) {
    while (nextAnnounced < announcedRounds.length && announcedRounds[nextAnnounced]! < limit) {
      const roundNumber = announcedRounds[nextAnnounced]!;
      nextAnnounced += 1;
      if (roundNumber !== currentRound && !rowIndexByRound.has(roundNumber)) {
        openRound(roundNumber);
      }
    }
  }

  for (const entry of messages) {
    const roundNumber = entry.round_number;
    if (roundNumber !== currentRound) {
      openAnnouncedBelow(roundNumber);
      openRound(roundNumber);
    }
    const isTurnStart = turn?.agentId !== entry.sender_agent_id;
    if (!turn || isTurnStart) {
      turn = {
        agentId: entry.sender_agent_id,
        timestamp: entry.timestamp,
        index: turn ? turn.index + 1 : 0,
      };
    }
    // Later messages in the same turn can supply the historical display name
    // used by its first entry, even when that first entry is reasoning/tool use.
    if (
      !turn.displayName &&
      entry.sender_display_name &&
      entry.sender_display_name !== turn.agentId
    ) {
      turn.displayName = entry.sender_display_name;
    }
    rowIndexByMessage.set(entry.message_id, rows.length);
    rows.push({
      kind: "entry",
      key: `entry-${entry.message_id}`,
      roundNumber,
      turn,
      isTurnStart,
      entry,
    });
  }
  openAnnouncedBelow(Number.POSITIVE_INFINITY);
  if (currentRound !== undefined) addBoundary("round-end", currentRound);
  return { rows, rowIndexByRound, rowIndexByMessage };
}

/** ``rows`` followed by the closing row, which holds what each agent answered
 *  once the run was over. It sits after the last round's end and counts as
 *  that round, so the round badge reads the last round while it is on screen. */
export function withClosingRow(rows: ChatRow[]): ChatRow[] {
  const lastRound = rows.at(-1)?.roundNumber ?? 0;
  return [...rows, { kind: "closing", key: "closing", roundNumber: lastRound }];
}
