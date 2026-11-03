"use client";

import { Check, X } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "../format";
import { isScenarioExtras, type RoundDetailPanelProps } from "../scenario-plugin";
import { colorHex, shapeGlyph } from "../shape-glyphs";
import { resultTeamId, TeamResultPill, teamDisplayName } from "../team-result-pill";

type IntersectionRoundCase = components["schemas"]["IntersectionRoundCase"];
type IntersectionSeatBoard = components["schemas"]["IntersectionSeatBoard"];
type IntersectionBoardObject = components["schemas"]["IntersectionBoardObject"];
type IntersectionSubmission = components["schemas"]["IntersectionSubmission"];
type RoundResult = components["schemas"]["RoundResult"];
type ObjectKind = components["schemas"]["ObjectKind"];

const ANSWER_KIND: ObjectKind = "answer";
const NEAR_MISS_KIND: ObjectKind = "near_miss";

function columnLetter(column: number): string {
  return String.fromCharCode("A".charCodeAt(0) + column);
}

function objectLine(obj: { color: string; shape: string; cell: string }): string {
  return `${obj.color} ${obj.shape} at ${obj.cell}`;
}

function ringClass(obj: IntersectionBoardObject): string {
  if (obj.kind === ANSWER_KIND) return "ring-2 ring-emerald-500";
  if (obj.kind === NEAR_MISS_KIND) return "ring-2 ring-amber-500";
  return "";
}

function BoardCell({ obj, teamSize }: { obj: IntersectionBoardObject | null; teamSize: number }) {
  if (obj === null) {
    return <div className="aspect-square rounded-[2px] bg-muted/40" />;
  }
  const faded = obj.boards_holding === 1;
  return (
    <div
      title={`${objectLine(obj)} · ${humanize(obj.kind)} · on ${obj.boards_holding} of ${teamSize} boards`}
      className={`flex aspect-square items-center justify-center rounded-[2px] bg-background text-[11px] leading-none ${ringClass(obj)}`}
      style={{ color: colorHex(obj.color), opacity: faded ? 0.4 : 1 }}
    >
      {shapeGlyph(obj.shape)}
    </div>
  );
}

function SeatBoard({
  board,
  gridSize,
  teamSize,
}: {
  board: IntersectionSeatBoard;
  gridSize: number;
  teamSize: number;
}) {
  const byCell = new Map<string, IntersectionBoardObject>();
  for (const obj of board.objects) byCell.set(`${obj.column},${obj.row}`, obj);
  const columns = Array.from({ length: gridSize }, (_, column) => column);
  return (
    <div>
      <div className="mb-1">
        <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Seat {board.seat_number}
        </div>
        <div
          className="truncate font-mono text-[10px] text-muted-foreground"
          title={board.agent_ids.join(" · ")}
        >
          {board.agent_ids.join(" · ")}
        </div>
      </div>
      <div
        className="grid gap-px rounded-md border border-border bg-muted/20 p-1"
        style={{ gridTemplateColumns: `auto repeat(${gridSize}, 1fr)` }}
      >
        <div />
        {columns.map(column => (
          <div key={column} className="text-center text-[8px] leading-3 text-muted-foreground">
            {columnLetter(column)}
          </div>
        ))}
        {columns.map(row => (
          <div key={row} className="contents">
            <div className="pr-0.5 text-right text-[8px] leading-none text-muted-foreground self-center">
              {row + 1}
            </div>
            {columns.map(column => (
              <BoardCell
                key={column}
                obj={byCell.get(`${column},${row}`) ?? null}
                teamSize={teamSize}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <span className="inline-block h-2.5 w-2.5 rounded-[2px] ring-2 ring-emerald-500" />
        answer, on every board
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="inline-block h-2.5 w-2.5 rounded-[2px] ring-2 ring-amber-500" />
        near-miss, on every board but one
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="opacity-40">●</span>
        on this board only
      </span>
      <span>hover an object for what it was placed as</span>
    </div>
  );
}

function SubmissionRow({ submission }: { submission: IntersectionSubmission }) {
  return (
    <li className="flex items-center gap-1.5 text-[12px] leading-relaxed">
      {submission.correct ? (
        <Check className="h-3 w-3 shrink-0 text-emerald-600" />
      ) : (
        <X className="h-3 w-3 shrink-0 text-rose-600" />
      )}
      <span className="font-mono text-[10px] text-muted-foreground">{submission.agent_id}</span>
      <span style={{ color: colorHex(submission.color) }}>{shapeGlyph(submission.shape)}</span>
      <span>{objectLine(submission)}</span>
    </li>
  );
}

function TeamCard({
  teamId,
  submissions,
  result,
  teamSize,
}: {
  teamId: string;
  submissions: IntersectionSubmission[];
  result: RoundResult | null;
  teamSize: number;
}) {
  return (
    <div className="rounded-md border border-border/70 bg-background px-3 py-2">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium">{teamDisplayName(teamId)}</span>
        <TeamResultPill result={result} />
      </div>
      <div className="mb-1 text-[11px] text-muted-foreground">
        {submissions.length} of {teamSize} viewers submitted
      </div>
      {submissions.length === 0 ? null : (
        <ol className="space-y-0.5">
          {submissions.map(submission => (
            <SubmissionRow key={submission.agent_id} submission={submission} />
          ))}
        </ol>
      )}
    </div>
  );
}

function teamIdsOf(roundResults: RoundResult[], submissions: IntersectionSubmission[]): string[] {
  return Array.from(
    new Set([...roundResults.map(resultTeamId), ...submissions.map(s => s.team_id)])
  ).sort();
}

function CaseHeader({ roundCase }: { roundCase: IntersectionRoundCase }) {
  const answer = roundCase.boards
    .flatMap(board => board.objects)
    .find(obj => obj.kind === ANSWER_KIND);
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <span className="text-sm font-medium">
        Find the one object on all {roundCase.team_size} boards
      </span>
      {answer !== undefined ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          <span style={{ color: colorHex(answer.color) }}>{shapeGlyph(answer.shape)}</span>
          {roundCase.answer_line}
        </span>
      ) : null}
      <span className="ml-auto text-[11px] text-muted-foreground">
        {roundCase.grid_size}×{roundCase.grid_size} grid · {roundCase.board_size} objects per board
        · {roundCase.decoy_count} decoy{roundCase.decoy_count === 1 ? "" : "s"}
      </span>
    </div>
  );
}

/** spot_the_intersection per-round detail: every seat's board, then each team's submissions. */
export function SpotTheIntersectionRoundDetailPanel({
  roundNumber,
  extras,
  roundResults,
}: RoundDetailPanelProps) {
  if (!isScenarioExtras(extras, "spot_the_intersection")) return null;
  const roundCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (roundCase === null) return null;

  const submissions = extras.submissions.filter(s => s.round_number === roundNumber);
  const resultByTeam = new Map(roundResults.map(r => [resultTeamId(r), r]));
  const sharedByTeams = roundCase.boards.some(board => board.agent_ids.length > 1);

  return (
    <div className="mb-5 space-y-3 rounded-lg border border-border bg-muted/40 p-3">
      <CaseHeader roundCase={roundCase} />

      <div>
        <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {sharedByTeams ? "Boards (both teams hold the same board at each seat)" : "Boards"}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {roundCase.boards.map(board => (
            <SeatBoard
              key={board.seat_number}
              board={board}
              gridSize={roundCase.grid_size}
              teamSize={roundCase.team_size}
            />
          ))}
        </div>
        <div className="mt-2">
          <Legend />
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Team submissions &amp; results
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {teamIdsOf(roundResults, submissions).map(teamId => (
            <TeamCard
              key={teamId}
              teamId={teamId}
              submissions={submissions.filter(s => s.team_id === teamId)}
              result={resultByTeam.get(teamId) ?? null}
              teamSize={roundCase.team_size}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
