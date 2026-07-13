import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/shared/lib/cn";

/**
 * Three-stage pipeline of how a run flows through the platform: configure and
 * launch a scenario from the CLI (knobs highlighted) → run it (logged, watchable
 * live) → evaluate the finished run with metrics (surfaced in the web UI). Each
 * stage carries a small visual echoing that part of the product.
 */
export function PlatformFlow() {
  return (
    <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
      <Stage
        n="1"
        title="Configure"
        body="Start a run from the command line. A config file sets the knobs, and you can override any of them inline."
      >
        <Terminal>
          <Line>
            <Prompt />
            python -m glossogen run <Scenario>veyru</Scenario> \
          </Line>
          <Line indent>--model claude-sonnet-4-6 --provider anthropic \</Line>
          <Line indent>
            <Knob>--config veyru/knobs_default.json round_count=20</Knob>
          </Line>
        </Terminal>
      </Stage>

      <Arrow />

      <Stage
        n="2"
        title="Run"
        body="The agents play out the rounds, each on its own loop (see below). Everything is recorded, and you can watch it happen live."
      >
        <LiveMock />
      </Stage>

      <Arrow />

      <Stage
        n="3"
        title="Evaluate"
        body="When it's done, score the run with whatever metrics you want. The numbers show up right in the web app."
      >
        <div className="flex w-full flex-col gap-2">
          <Terminal>
            <Line>
              <Prompt />
              python -m glossogen evaluate <Scenario>veyru</Scenario> \
            </Line>
            <Line indent>--run-dir runs/veyru/1742234567 \</Line>
            <Line indent>
              <Knob>--metrics round_success,shorthand_codes</Knob>
            </Line>
          </Terminal>
          <MetricsMock />
        </div>
      </Stage>
    </div>
  );
}

function Arrow() {
  return (
    <ChevronRight className="mx-auto h-5 w-5 rotate-90 self-center text-muted-foreground/40 lg:rotate-0" />
  );
}

function Stage({
  n,
  title,
  body,
  children,
}: {
  n: string;
  title: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4">{children}</div>
      <div className="mt-auto flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
          {n}
        </span>
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{body}</p>
    </div>
  );
}

/* --- Configure / Evaluate: a small terminal showing the real CLI command --- */

function Terminal({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-neutral-900 shadow-sm">
      <div className="flex items-center gap-1.5 border-b border-white/10 px-3 py-1.5">
        <span className="h-2 w-2 rounded-full bg-white/20" />
        <span className="h-2 w-2 rounded-full bg-white/20" />
        <span className="h-2 w-2 rounded-full bg-white/20" />
      </div>
      <div className="overflow-x-auto px-3 py-2.5 font-mono text-[10px] leading-relaxed text-neutral-300">
        {children}
      </div>
    </div>
  );
}

function Line({ children, indent }: { children: ReactNode; indent?: boolean }) {
  return <div className={cn("whitespace-pre", indent && "pl-4")}>{children}</div>;
}

function Prompt() {
  return <span className="text-neutral-500">$ </span>;
}

function Scenario({ children }: { children: ReactNode }) {
  return <span className="text-sky-300">{children}</span>;
}

function Knob({ children }: { children: ReactNode }) {
  return <span className="rounded bg-amber-400/15 px-1 text-amber-300">{children}</span>;
}

/* --- Run: the live channel panel (unchanged) --- */

function LiveMock() {
  return (
    <div className="flex h-24 w-full items-center justify-center overflow-hidden rounded-xl border border-border/60 bg-muted/40 px-4">
      <div className="flex w-full flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-muted-foreground">#link</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[8px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75 motion-reduce:hidden" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            live
          </span>
        </div>
        <span className="h-2 w-3/4 rounded-full bg-blue-500/30" />
        <span className="ml-auto h-2 w-2/3 rounded-full bg-violet-500/30" />
        <span className="h-2 w-1/2 rounded-full bg-blue-500/30" />
      </div>
    </div>
  );
}

/* --- Evaluate: a compact mock of the web-UI metrics panel --- */

const METRIC_ROWS = [
  { name: "Round success", value: "0.80" },
  { name: "Shorthand codes", value: "5.0" },
  { name: "Language strangeness", value: "3.0" },
];

function MetricsMock() {
  return (
    <div className="w-full rounded-lg border border-border bg-background p-2.5">
      <div className="mb-1 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
        Metrics
      </div>
      <div className="divide-y divide-border">
        {METRIC_ROWS.map(row => (
          <div key={row.name} className="flex items-center justify-between py-1 text-[10px]">
            <span className="truncate text-foreground">{row.name}</span>
            <span className="font-mono text-muted-foreground">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
