import { RunList } from "@/features/runs/run-list";

export default function RunsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="mb-8 text-3xl font-bold tracking-tight">Simulation Runs</h1>
      <RunList />
    </main>
  );
}
