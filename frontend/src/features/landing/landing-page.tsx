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
            Study how AI agents talk to each other
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
            In GlossoGen, you drop a handful of agents into a scenario, give them a shared goal, and
            let them work it out over a series of rounds, deciding on their own what to say and when
            to act. Every message and move is logged, so once a run finishes you can replay it and
            measure what happened.
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
              On their own, the agents just talk in plain English. Two things push them to tighten
              it up:
            </p>
            <ul className="mt-6 flex flex-col gap-5">
              <li className="flex gap-3">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground">
                  <Gauge className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-sm font-medium">Pressure inside a round</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                    Give them a tight character budget and every word starts to cost. Ramble on, and
                    they run out of room before the job is done.
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
                    Between rounds they get a quiet moment off the budget to compare notes and
                    settle on shorthand. The next round, they put it to use.
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
              You bring the question. GlossoGen comes with the scenarios, runs the agents and their
              loops, and gives you the metrics to pick apart what happened.
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
              Under the hood, every agent just runs the same loop over and over: wait for something
              to happen, then pick a tool, maybe reading the channel, sending a message, or acting
              on the world.
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
