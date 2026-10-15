import type { DisplayEntry } from "./display-entry";

interface Turn {
  agentId: string;
  timestamp: string;
  index: number;
  displayName?: string;
}

export type ChatRow =
  | { kind: "round-start" | "round-end"; key: string; roundNumber: number }
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
