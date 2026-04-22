import { RunDetail } from "@/features/runs/run-detail";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ scenario: string; runDirName: string }>;
}) {
  const { scenario, runDirName } = await params;
  const runId = `${scenario}/${runDirName}`;
  return <RunDetail key={runId} scenario={scenario} runDirName={runDirName} />;
}
