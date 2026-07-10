import Link from "next/link";
import { ArrowRight, Gauge, Github, MessagesSquare } from "lucide-react";
import { CommsAnimation } from "./comms-animation";
import { AgentLoopAnimation } from "./agent-loop-animation";
import { EmergenceAnimation } from "./emergence-animation";
import { PlatformFlow } from "./platform-flow";

/** Public source repository for GlossoGen. */
const GITHUB_URL = "https://github.com/agencyenterprise/GlossoGen";

/**
 * Public landing page shown at the app root to first-time visitors.
 *
 * Introduces the platform and links into the guided, no-auth walkthrough of a
 * real run at /demo. ``appHref`` / ``appLabel`` drive the header call to action:
 * "Dashboard" for a logged-in visitor (local mode), "Research team login"
 * otherwise (signed-out Clerk mode).
 */
export function LandingPage({ appHref, appLabel }: { appHref: string; appLabel: string }) {
  return (
    <main className="min-h-dvh bg-background text-foreground">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="h-2.5 w-2.5 rounded-full bg-primary" />
          GlossoGen
        </span>
        <div className="flex items-center gap-2">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Github className="h-4 w-4" /> GitHub
          </a>
          <Link
            href={appHref}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {appLabel}
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-10 px-6 pt-10 pb-16 lg:grid-cols-[1.05fr_1fr] lg:pt-16 lg:pb-24">
        <div>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Study how AI agents communicate
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            GlossoGen is a platform for researchers to analyze how AI agents communicate. It offers
            many scenarios, each a series of rounds with a specific goal the agents must reach —
            working together and deciding on their own what to do. Every message, tool call, and
            outcome is logged, and when a run finishes, evaluators extract insights from it.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              href="/demo"
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Explore one simulation <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
        <div className="flex justify-center lg:justify-end">
          <CommsAnimation />
        </div>
      </section>

      {/* How language emerges */}
      <section className="border-t border-border bg-muted/30">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-16 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">How language emerges</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              Two scenario mechanics push the agents to communicate effectively:
            </p>
            <ul className="mt-6 flex flex-col gap-5">
              <li className="flex gap-3">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground">
                  <Gauge className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-sm font-medium">Pressure inside a round</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                    A scenario can put the agents under pressure — here, a budget where every
                    character counts — so being verbose costs them the round.
                  </p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground">
                  <MessagesSquare className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-sm font-medium">Reflection between rounds</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                    An off-the-clock postmortem lets them review what happened and agree on a
                    sharper protocol — which they put to use on the next round.
                  </p>
                </div>
              </li>
            </ul>
          </div>
          <div className="flex justify-center lg:justify-end">
            <EmergenceAnimation />
          </div>
        </div>
      </section>

      {/* Running an experiment */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-bold tracking-tight">Running an experiment</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              GlossoGen provides the scenarios, manages the agents and their loops, and gives you
              the evaluators to make sense of each run.
            </p>
          </div>
          <div className="mt-8">
            <PlatformFlow />
          </div>
        </div>
      </section>

      {/* The agent loop */}
      <section className="border-t border-border bg-muted/30">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-bold tracking-tight">The agent loop</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              Each agent runs its own loop: wait for new activity, then call whatever tools it
              chooses — read the channel, send a message, or act on the world — again and again.
            </p>
          </div>
          <div className="mt-8">
            <AgentLoopAnimation />
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-center px-6 py-6 text-[12px] text-muted-foreground">
          Powered by
          <a
            href="https://ae.studio/alignment"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 font-medium text-foreground hover:underline"
          >
            AE Studio
          </a>
        </div>
      </footer>
    </main>
  );
}
