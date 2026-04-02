import { BranchesTimeline } from "@/features/branches/branches-timeline";

export default async function BranchesTimelinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <BranchesTimeline key={id} runId={id} />;
}
