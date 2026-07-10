"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, XCircle } from "lucide-react";
import { loadDemoRun } from "@/features/onboarding/demo-run";
import { PublicRunViewer } from "@/features/runs/public-run-viewer";

/**
 * Public, unauthenticated walkthrough of one real simulation run.
 *
 * Loads the frozen demo snapshot (a static asset) and renders it through the
 * real run viewer in read-only mode, with a guided tour of the interface.
 */
export default function DemoPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["demo-run"],
    queryFn: loadDemoRun,
    staleTime: Infinity,
  });

  if (isLoading) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-2 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load the demo run</p>
      </div>
    );
  }

  return <PublicRunViewer run={data} />;
}
