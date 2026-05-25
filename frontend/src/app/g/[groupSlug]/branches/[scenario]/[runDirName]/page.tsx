import { BranchesTimeline } from "@/features/branches/branches-timeline";

export default async function BranchesTimelinePage({
  params,
}: {
  params: Promise<{ scenario: string; runDirName: string }>;
}) {
  const { scenario, runDirName } = await params;
  const runId = `${scenario}/${runDirName}`;
  return <BranchesTimeline key={runId} runId={runId} />;
}
