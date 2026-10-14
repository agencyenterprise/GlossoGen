"use client";

/**
 * The server's files as a round ended, at the top of the round-timeline modal.
 *
 * A tree on the left; selecting a file shows its content with who wrote it,
 * who can read it, and the last change made to it. Files changed during the
 * round are marked, and a file both agents can read is marked shared.
 */

import { File, Folder } from "lucide-react";
import { useState } from "react";
import { cn } from "@/shared/lib/cn";
import type { RoundDetailPanelProps } from "../scenario-plugin";
import { type DeadDropFile, isDeadDropExtras } from "./dead-drop-extras";
import { buildFileTree, displayPath, type FileTreeNode } from "./filesystem-tree";

const SHARED_READER_COUNT = 2;

function isShared(file: DeadDropFile): boolean {
  return file.readers.length >= SHARED_READER_COUNT;
}

interface TreeRowProps {
  node: FileTreeNode;
  depth: number;
  roundNumber: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

function TreeRow({ node, depth, roundNumber, selectedPath, onSelect }: TreeRowProps) {
  const file = node.file;
  const indent = { paddingLeft: `${depth * 12 + 4}px` };
  if (file === null) {
    return (
      <>
        <div className="flex items-center gap-1 py-0.5 text-muted-foreground" style={indent}>
          <Folder className="h-3 w-3 shrink-0" />
          <span>{node.name}</span>
        </div>
        {node.children.map(child => (
          <TreeRow
            key={child.displayPath}
            node={child}
            depth={depth + 1}
            roundNumber={roundNumber}
            selectedPath={selectedPath}
            onSelect={onSelect}
          />
        ))}
      </>
    );
  }
  const changedThisRound = file.last_changed_round === roundNumber;
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-1 rounded py-0.5 text-left hover:bg-muted",
        selectedPath === node.displayPath && "bg-muted font-medium"
      )}
      style={indent}
      onClick={() => onSelect(node.displayPath)}
    >
      <File className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="truncate">{node.name}</span>
      {changedThisRound ? (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
          title={`changed in round ${roundNumber}`}
        />
      ) : null}
      {isShared(file) ? (
        <span className="ml-auto shrink-0 text-[9px] uppercase text-emerald-500">shared</span>
      ) : null}
    </button>
  );
}

function FileDetail({ file }: { file: DeadDropFile }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 break-all font-mono text-[11px] font-medium">
        {displayPath(file.path, file.tmp_of)}
      </div>
      <div className="mb-2 space-y-0.5 text-[10px] text-muted-foreground">
        <div>written by: {file.authors.join(", ") || "nobody"}</div>
        <div>readable by: {file.readers.join(", ")}</div>
        <div>
          last changed by {file.last_changed_by}
          {file.last_changed_round > 0 ? ` in round ${file.last_changed_round}` : " at setup"}
        </div>
      </div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded bg-background p-2 font-mono text-[10px]">
        {file.content === "" ? "(empty)" : file.content}
      </pre>
    </div>
  );
}

function findFile(node: FileTreeNode, path: string): DeadDropFile | null {
  if (node.displayPath === path && node.file !== null) return node.file;
  for (const child of node.children) {
    const found = findFile(child, path);
    if (found !== null) return found;
  }
  return null;
}

/** The server's files at the end of round `roundNumber`, from the run's dead_drop extras. */
export function DeadDropFilesystemPanel({ roundNumber, extras }: RoundDetailPanelProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  if (!isDeadDropExtras(extras)) return null;
  const round = extras.rounds.find(candidate => candidate.round_number === roundNumber);
  if (round === undefined) return null;
  const tree = buildFileTree(round);
  const changed = round.files.filter(file => file.last_changed_round === roundNumber).length;
  const selected = selectedPath === null ? null : findFile(tree, selectedPath);
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Filesystem at the end of round {roundNumber}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {round.files.length} file{round.files.length === 1 ? "" : "s"} · {changed} changed this
          round
        </span>
      </div>
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 text-[11px]">
        <div className="max-h-72 overflow-auto font-mono">
          {tree.children.map(child => (
            <TreeRow
              key={child.displayPath}
              node={child}
              depth={0}
              roundNumber={roundNumber}
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
            />
          ))}
        </div>
        {selected === null ? (
          <div className="self-center text-center text-[11px] text-muted-foreground">
            Select a file to see its content.
          </div>
        ) : (
          <FileDetail file={selected} />
        )}
      </div>
    </div>
  );
}
