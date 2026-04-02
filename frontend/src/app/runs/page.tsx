import { GitFork, Plus } from "lucide-react";
import Link from "next/link";
import { RunList } from "@/features/runs/run-list";

export default function RunsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Simulation Runs</h1>
        <div className="flex items-center gap-2">
          <Link
            href="/runs/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Start New Simulation
          </Link>
          <Link
            href="/branches"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <GitFork className="h-4 w-4" />
            Branches
          </Link>
        </div>
      </div>
      <RunList />
    </main>
  );
}
