"use client";

import { Check, X } from "lucide-react";
import type { components } from "@/types/api.gen";
import type { RoundDetailPanelProps } from "../scenario-plugin";

type SpotExtras = components["schemas"]["SpotTheDifferenceRunExtras"];
type SpotObject = components["schemas"]["SpotObject"];
type SpotPlantedDifference = components["schemas"]["SpotPlantedDifference"];
type SpotSubmissionMetadata = components["schemas"]["SpotSubmissionMetadata"];
type SpotTeamRoundResult = components["schemas"]["SpotTeamRoundResult"];

const SHAPE_GLYPH: Record<string, string> = {
  circle: "●",
  square: "■",
  triangle: "▲",
  star: "★",
};

const COLOR_HEX: Record<string, string> = {
  red: "#ef4444",
  blue: "#3b82f6",
  green: "#22c55e",
  yellow: "#eab308",
  purple: "#a855f7",
  orange: "#f97316",
  pink: "#ec4899",
  brown: "#a16207",
};

const KIND_LABEL: Record<string, string> = {
  attribute_changed: "attribute changed",
  object_moved: "moved",
  object_added: "added",
  object_removed: "removed",
};

const TEAM_LABEL: Record<string, string> = {
  team_a: "Team A",
  team_b: "Team B",
  solo: "Team",
};

function isSpotExtras(extras: unknown): extras is SpotExtras {
  if (typeof extras !== "object" || extras === null) return false;
  return (extras as { scenario_name?: string }).scenario_name === "spot_the_difference";
}

function cellKey(obj: SpotObject): string {
  return `${obj.column},${obj.row}`;
}

function glyph(obj: SpotObject): string {
  return SHAPE_GLYPH[obj.shape] ?? "●";
}

function objectColor(obj: SpotObject): string {
  return COLOR_HEX[obj.color] ?? "#6b7280";
}

function SceneGrid({
  label,
  objects,
  gridSize,
  highlight,
}: {
  label: string;
  objects: SpotObject[];
  gridSize: number;
  highlight: Set<string>;
}) {
  const byCell = new Map<string, SpotObject>();
  for (const obj of objects) byCell.set(cellKey(obj), obj);
  const rows = [];
  for (let row = 1; row <= gridSize; row++) {
    const cells = [];
    for (let column = 1; column <= gridSize; column++) {
      const key = `${column},${row}`;
      const obj = byCell.get(key) ?? null;
      const isDiff = highlight.has(key);
      cells.push(
        <div
          key={key}
          title={obj ? `${obj.size} ${obj.color} ${obj.shape} (${obj.region})` : undefined}
          className={`flex aspect-square items-center justify-center rounded-[2px] text-[9px] leading-none ${
            isDiff ? "ring-2 ring-amber-500 ring-offset-0" : ""
          } ${obj || isDiff ? "bg-background" : "bg-muted/40"}`}
          style={obj ? { color: objectColor(obj) } : undefined}
        >
          {obj ? (
            <span style={{ fontSize: obj.size === "large" ? "11px" : "8px" }}>{glyph(obj)}</span>
          ) : (
            ""
          )}
        </div>
      );
    }
    rows.push(
      <div
        key={row}
        className="grid gap-px"
        style={{ gridTemplateColumns: `repeat(${gridSize}, 1fr)` }}
      >
        {cells}
      </div>
    );
  }
  return (
    <div className="flex-1">
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="space-y-px rounded-md border border-border bg-muted/20 p-1">{rows}</div>
    </div>
  );
}

function DifferenceRow({ diff, index }: { diff: SpotPlantedDifference; index: number }) {
  return (
    <li className="flex gap-2 text-[12px] leading-relaxed">
      <span className="mt-0.5 font-mono text-[10px] text-muted-foreground">{index + 1}.</span>
      <div>
        <span className="mr-1.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">
          {KIND_LABEL[diff.kind] ?? diff.kind}
        </span>
        <span className="text-foreground">{diff.description}</span>
      </div>
    </li>
  );
}

function ResultPill({ result }: { result: SpotTeamRoundResult | null }) {
  if (result === null) {
    return <span className="text-[11px] text-muted-foreground">no result recorded</span>;
  }
  const tone = result.success
    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
    : "bg-rose-500/15 text-rose-700 dark:text-rose-400";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}
    >
      {result.success ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {result.reason}
    </span>
  );
}

function TeamCard({
  teamId,
  submission,
  result,
}: {
  teamId: string;
  submission: SpotSubmissionMetadata | null;
  result: SpotTeamRoundResult | null;
}) {
  return (
    <div className="rounded-md border border-border/70 bg-background px-3 py-2">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium">{TEAM_LABEL[teamId] ?? teamId}</span>
        <ResultPill result={result} />
      </div>
      {submission === null ? (
        <div className="text-[11px] italic text-muted-foreground">
          No submission this round (ran out of budget or time).
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="text-[11px] text-muted-foreground">
            {submission.found_all ? "found all" : "incomplete"} ·{" "}
            {submission.matched_difference_indices.length} matched ·{" "}
            {submission.false_positive_count} false positive
            {submission.false_positive_count === 1 ? "" : "s"} ·{" "}
            {submission.characters_at_submission} chars
          </div>
          <ol className="space-y-0.5">
            {submission.submitted_items.map((item, i) => (
              <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed">
                <span className="mt-0.5 font-mono text-[10px] text-muted-foreground">{i + 1}.</span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
          {submission.explanation !== "" ? (
            <div className="rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
              <span className="text-[10px] uppercase tracking-wide">judge</span>{" "}
              {submission.explanation}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** spot_the_difference per-round detail rendered at the top of the round-timeline modal. */
export function SpotTheDifferenceRoundDetailPanel({ roundNumber, extras }: RoundDetailPanelProps) {
  if (!isSpotExtras(extras)) return null;
  const diffCase = extras.cases.find(c => c.round_number === roundNumber) ?? null;
  if (diffCase === null) return null;

  const highlightA = new Set<string>();
  const highlightB = new Set<string>();
  for (const diff of diffCase.differences) {
    if (diff.scene_a_object !== null) highlightA.add(cellKey(diff.scene_a_object));
    if (diff.scene_b_object !== null) highlightB.add(cellKey(diff.scene_b_object));
  }

  const submissions = Object.values(extras.submission_metadata_by_call_id).filter(
    s => s.round_number === roundNumber
  );
  const results = extras.team_results.filter(r => r.round_number === roundNumber);
  const teamIds = Array.from(
    new Set([...results.map(r => r.team_id ?? "solo"), ...submissions.map(s => s.team_id)])
  ).sort();
  const submissionByTeam = new Map(submissions.map(s => [s.team_id, s]));
  const resultByTeam = new Map(results.map(r => [r.team_id ?? "solo", r]));

  return (
    <div className="mb-5 space-y-3 rounded-lg border border-border bg-muted/40 p-3">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Case {diffCase.case_number}
        </span>
        <span className="text-sm font-medium">
          {diffCase.difference_count} difference{diffCase.difference_count === 1 ? "" : "s"} to find
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {diffCase.grid_size}×{diffCase.grid_size} grid · {diffCase.scene_a.length} vs{" "}
          {diffCase.scene_b.length} objects
        </span>
      </div>

      <div className="flex gap-3">
        <SceneGrid
          label="Scene A (left viewer)"
          objects={diffCase.scene_a}
          gridSize={diffCase.grid_size}
          highlight={highlightA}
        />
        <SceneGrid
          label="Scene B (right viewer)"
          objects={diffCase.scene_b}
          gridSize={diffCase.grid_size}
          highlight={highlightB}
        />
      </div>

      <div>
        <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Differences (highlighted above)
        </div>
        <ol className="space-y-1">
          {diffCase.differences.map((diff, i) => (
            <DifferenceRow key={i} diff={diff} index={i} />
          ))}
        </ol>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Team submissions &amp; results
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {teamIds.map(teamId => (
            <TeamCard
              key={teamId}
              teamId={teamId}
              submission={submissionByTeam.get(teamId) ?? null}
              result={resultByTeam.get(teamId) ?? null}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
