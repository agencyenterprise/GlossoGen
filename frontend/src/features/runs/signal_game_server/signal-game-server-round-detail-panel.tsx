"use client";

import type { components } from "@/types/api.gen";
import type { RoundDetailPanelProps } from "../scenario-plugin";

type SignalGameServerExtras = components["schemas"]["SignalGameServerRunExtras"];
type SignalGameServerJudgement = components["schemas"]["SignalGameServerJudgement"];
type SignalGameServerJudgedTextView = components["schemas"]["SignalGameServerJudgedTextView"];
type SignalGameServerCheat = components["schemas"]["SignalGameServerCheat"];
type JudgeToolCall = components["schemas"]["JudgeToolCall"];

const KIND_LABEL: Record<string, string> = {
  name: "name",
  content: "content",
  command: "command line",
};

const TOOL_LABEL: Record<string, string> = {
  run_command: "shell",
  run_python: "python",
};

function isSignalGameServerExtras(extras: unknown): extras is SignalGameServerExtras {
  if (typeof extras !== "object" || extras === null) return false;
  return (extras as { scenario_name?: string }).scenario_name === "signal_game_server";
}

function KindBadge({ kind }: { kind: string }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
      {KIND_LABEL[kind] ?? kind}
    </span>
  );
}

function VerdictBadge({ flagged }: { flagged: boolean }) {
  if (flagged) {
    return (
      <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-medium text-red-700 dark:text-red-400">
        flagged
      </span>
    );
  }
  return (
    <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-400">
      passed
    </span>
  );
}

function TextBlock({ text }: { text: string }) {
  return (
    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded border border-border/60 bg-background px-2 py-1 font-mono text-[11px] leading-snug">
      {text}
    </pre>
  );
}

function JudgedTextRow({ text }: { text: SignalGameServerJudgedTextView }) {
  return (
    <li className="rounded-md border border-border/70 bg-background/60 px-2.5 py-1.5">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="font-mono text-[10px] text-muted-foreground">{text.number}.</span>
        <KindBadge kind={text.kind} />
        <span className="font-mono">{text.path}</span>
        <span className="text-muted-foreground">by {text.author}</span>
        <VerdictBadge flagged={text.flagged} />
      </div>
      <TextBlock text={text.text} />
      {text.kind === "command" && text.output !== "" ? (
        <>
          <div className="mt-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Printed
          </div>
          <TextBlock text={text.output} />
        </>
      ) : null}
      {text.reason !== null ? (
        <div className="mt-1 text-[11px] text-muted-foreground">{text.reason}</div>
      ) : null}
    </li>
  );
}

function TreeFindingRow({ cheat }: { cheat: SignalGameServerCheat }) {
  return (
    <li className="rounded-md border border-border/70 bg-background/60 px-2.5 py-1.5">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <KindBadge kind={cheat.kind} />
        <span className="font-mono">{cheat.path}</span>
        <span className="text-muted-foreground">by {cheat.author}</span>
        <VerdictBadge flagged={true} />
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground">{cheat.reason}</div>
    </li>
  );
}

function ToolCallRow({ call, index }: { call: JudgeToolCall; index: number }) {
  const firstLine = call.input.split("\n")[0] ?? "";
  return (
    <details className="rounded-md border border-border/70 bg-background/60 px-2.5 py-1.5">
      <summary className="cursor-pointer text-[11px]">
        <span className="font-mono text-[10px] text-muted-foreground">{index + 1}.</span>{" "}
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {TOOL_LABEL[call.tool] ?? call.tool}
        </span>{" "}
        <span className="font-mono">{firstLine}</span>
      </summary>
      <div className="mt-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        Input
      </div>
      <TextBlock text={call.input} />
      <div className="mt-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        Output
      </div>
      <TextBlock text={call.output} />
    </details>
  );
}

function JudgementView({ judgement }: { judgement: SignalGameServerJudgement }) {
  const flaggedCount =
    judgement.texts.filter(text => text.flagged).length + judgement.flagged_from_tree.length;
  return (
    <div className="space-y-2">
      <div className="text-[11px] text-muted-foreground">
        {judgement.texts.length} text{judgement.texts.length === 1 ? "" : "s"} read · {flaggedCount}{" "}
        flagged · {judgement.tool_calls.length} tool call
        {judgement.tool_calls.length === 1 ? "" : "s"}
      </div>
      {judgement.texts.length > 0 ? (
        <ol className="space-y-1.5">
          {judgement.texts.map(text => (
            <JudgedTextRow key={text.number} text={text} />
          ))}
        </ol>
      ) : null}
      {judgement.flagged_from_tree.length > 0 ? (
        <div>
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Flagged from the tree
          </div>
          <ul className="space-y-1.5">
            {judgement.flagged_from_tree.map(cheat => (
              <TreeFindingRow key={`${cheat.kind}:${cheat.path}`} cheat={cheat} />
            ))}
          </ul>
        </div>
      ) : null}
      {judgement.tool_calls.length > 0 ? (
        <div>
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Tool calls
          </div>
          <div className="space-y-1.5">
            {judgement.tool_calls.map((call, index) => (
              <ToolCallRow key={index} call={call} index={index} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The plaintext judge's reading of this round: the texts it was shown with its decision
 * on each, the names it flagged from the tree, and the tool calls it made.
 */
export function SignalGameServerRoundDetailPanel({ roundNumber, extras }: RoundDetailPanelProps) {
  if (!isSignalGameServerExtras(extras)) return null;
  const judgement =
    extras.judgements.find(candidate => candidate.round_number === roundNumber) ?? null;
  return (
    <section className="mb-4 rounded-md border border-border bg-muted/20 px-3 py-2">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Judge
      </div>
      {judgement === null ? (
        <div className="text-[11px] italic text-muted-foreground">
          Not called this round: nothing new on the server to read.
        </div>
      ) : (
        <JudgementView judgement={judgement} />
      )}
    </section>
  );
}
