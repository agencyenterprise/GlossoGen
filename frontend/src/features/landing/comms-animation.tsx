import { Check, Lock, Wrench } from "lucide-react";
import { cn } from "@/shared/lib/cn";

/**
 * Looping hero illustration of the core loop: two agents exchanging messages on
 * a shared, budget-constrained channel, their language compressing from full
 * sentences to terse codes, ending in a judged tool call. Pure CSS animation
 * (keyframes in globals.css); respects prefers-reduced-motion.
 */
export function CommsAnimation() {
  return (
    <div className="w-full max-w-md rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-muted-foreground">#</span>
          <span className="text-[13px] font-medium">link</span>
          <span className="text-[11px] text-muted-foreground">comm link</span>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
          budget 250c
        </span>
      </div>

      <div className="mb-3 flex items-start gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500 text-[10px] font-semibold text-white">
          A1
        </span>
        <div className="flex-1 rounded-md border border-amber-300/40 bg-amber-50 px-2.5 py-1.5 text-amber-800 dark:border-amber-800/40 dark:bg-amber-950/30 dark:text-amber-300">
          <div className="mb-1 flex items-center gap-1 text-[9px] font-medium uppercase tracking-wide text-amber-700/80 dark:text-amber-400/80">
            <Lock className="h-2.5 w-2.5" /> private · only A1
          </div>
          <div className="text-[11px] leading-snug">
            <span className="font-medium">New task: save the alien being.</span> What you observe:
            the corners are dim, several edges are fading, the perimeter is losing light, and the
            hum sounds thin and hollow at the edges.
          </div>
        </div>
      </div>

      <div className="flex min-h-[248px] flex-col gap-2">
        <MessageRow
          who="FO"
          side="left"
          text="corners dim, edges fading; hum thin"
          cost="41c"
          animClass="comms-1"
        />
        <MessageRow
          who="SE"
          side="right"
          text="drape cloth on back face 8s, gentle"
          cost="38c"
          animClass="comms-2"
        />
        <MessageRow who="FO" side="left" text="DE" cost="2c" mono animClass="comms-3" />
        <MessageRow who="SE" side="right" text="P13L8g" cost="6c" mono animClass="comms-4" />

        <div className="comms-5 flex justify-start pl-9">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/60 px-2.5 py-1.5 text-[11px]">
            <Wrench className="h-3 w-3 text-muted-foreground" />
            <span className="font-mono">
              stabilize_veyru(
              <span className="text-muted-foreground">&quot;press faces…&quot;</span>)
            </span>
          </span>
        </div>

        <div className="comms-6 flex justify-start pl-9">
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
            <Check className="h-3 w-3" /> stabilized · round passed
          </span>
        </div>
      </div>
    </div>
  );
}

const AVATAR_STYLES: Record<"FO" | "SE", string> = {
  FO: "bg-blue-500 text-white",
  SE: "bg-violet-500 text-white",
};

function MessageRow({
  who,
  side,
  text,
  cost,
  mono,
  animClass,
}: {
  who: "FO" | "SE";
  side: "left" | "right";
  text: string;
  cost: string;
  mono?: boolean;
  animClass: string;
}) {
  const avatar = (
    <span
      className={cn(
        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
        AVATAR_STYLES[who]
      )}
    >
      {who === "FO" ? "A1" : "A2"}
    </span>
  );
  return (
    <div
      className={cn(animClass, "flex items-start gap-2", side === "right" && "flex-row-reverse")}
    >
      {avatar}
      <div className="flex max-w-[78%] items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-1.5">
        <span className={cn("text-[12px] leading-snug", mono && "font-mono")}>{text}</span>
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{cost}</span>
      </div>
    </div>
  );
}
