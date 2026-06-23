import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
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
 * In Clerk mode the layout gates the whole `/g/<slug>` subtree: a
 * signed-out request is sent to `/sign-in` (preserving the deep link as
 * the post-login destination) before any child page renders. The proxy's
 * `auth.protect()` does not redirect on these routes because
 * `organizationSyncOptions` rewrites `/g/:slug` first, so the server-side
 * check here is what actually protects direct links to a run. In local
 * mode (no Clerk publishable key) the check is skipped.
 *
 * The layout also mounts a top bar with ``<OrganizationSwitcher>``;
 * clicking another org navigates to ``/g/<otherSlug>/runs`` (no
 * ``setActive`` call needed — the next request's JWT membership claim is
 * checked against the URL slug).
 */
export default async function GroupLayout({
  params,
  children,
}: {
  params: Promise<{ groupSlug: string | string[] }>;
  children: ReactNode;
}) {
  if (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    const { userId } = await auth();
    if (userId === null || userId === undefined) {
      redirect("/sign-in");
    }
  }
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
