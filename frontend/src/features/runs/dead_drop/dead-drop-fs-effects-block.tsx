/**
 * The files one `run_command` call changed or read, beneath the tool call.
 *
 * A change the other agent can see is marked visible to the other agent; a
 * read names who wrote what was read. Repeats in a row show once with a count.
 */

import { cn } from "@/shared/lib/cn";
import type { DeadDropFsEffect } from "./dead-drop-extras";

const KIND_CLASS: Record<DeadDropFsEffect["kind"], string> = {
  write: "text-emerald-500",
  append: "text-emerald-500",
  copy: "text-emerald-500",
  move: "text-emerald-500",
  mkdir: "text-muted-foreground",
  touch: "text-muted-foreground",
  remove: "text-red-500",
  read: "text-blue-500",
};

function EffectRow({ effect }: { effect: DeadDropFsEffect }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-1.5">
      <span className={cn("w-12 shrink-0 font-medium", KIND_CLASS[effect.kind])}>
        {effect.kind}
      </span>
      <span className="break-all">{effect.path}</span>
      {effect.destination !== null ? (
        <span className="break-all">→ {effect.destination}</span>
      ) : null}
      {effect.count > 1 ? <span className="text-muted-foreground">×{effect.count}</span> : null}
      {effect.kind === "read" && effect.authors.length > 0 ? (
        <span className="text-muted-foreground">written by {effect.authors.join(", ")}</span>
      ) : null}
      {effect.kind !== "read" && effect.shared ? (
        <span className="text-emerald-500">visible to the other agent</span>
      ) : null}
    </div>
  );
}

export function DeadDropFsEffectsBlock({ effects }: { effects: DeadDropFsEffect[] }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Filesystem
      </div>
      <div className="space-y-0.5 rounded bg-muted p-2 font-mono text-[10px]">
        {effects.map((effect, index) => (
          <EffectRow key={index} effect={effect} />
        ))}
      </div>
    </div>
  );
}
