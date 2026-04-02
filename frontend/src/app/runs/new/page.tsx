import { NewSimulationForm } from "@/features/runs/new-simulation-form";

export default function NewSimulationPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="mb-8 text-3xl font-bold tracking-tight">Start New Simulation</h1>
      <NewSimulationForm />
    </main>
  );
}
