import type { ReactNode } from "react";
import { GroupProvider } from "@/features/auth/group-context";
import { GroupTopBar } from "@/features/auth/group-top-bar";

/**
 * Group-scoped layout segment.
 *
 * Every `/g/[groupSlug]/...` route shares this layout. It exposes the
 * URL's slug via :func:`useActiveGroupSlug` to the rest of the app —
 * including the api-client middleware, which uses it to substitute
 * ``{group_slug}`` in outgoing REST URLs.
 *
 * In Clerk mode the layout also mounts a top bar with
 * ``<OrganizationSwitcher>``; clicking another org navigates to
 * ``/g/<otherSlug>/runs`` (no ``setActive`` call needed — the next
 * request's JWT membership claim is checked against the URL slug).
 */
export default async function GroupLayout({
  params,
  children,
}: {
  params: Promise<{ groupSlug: string | string[] }>;
  children: ReactNode;
}) {
  const resolved = await params;
  const raw = resolved.groupSlug;
  const groupSlug = Array.isArray(raw) ? (raw[0] ?? "") : raw;
  return (
    <GroupProvider slug={groupSlug}>
      <GroupTopBar />
      {children}
    </GroupProvider>
  );
}
