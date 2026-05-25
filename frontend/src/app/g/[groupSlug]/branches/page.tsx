"use client";

import { List } from "lucide-react";
import Link from "next/link";
import { BranchesList } from "@/features/branches/branches-list";
import { useGroupPath } from "@/features/auth/group-context";

export default function BranchesPage() {
  const groupPath = useGroupPath();
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Branches</h1>
        <Link
          href={groupPath("/runs")}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <List className="h-4 w-4" />
          All Runs
        </Link>
      </div>
      <BranchesList />
    </main>
  );
}
