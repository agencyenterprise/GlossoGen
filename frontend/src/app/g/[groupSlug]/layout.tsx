import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { readSession } from "@/features/auth/adapter/server";
import { GroupProvider } from "@/features/auth/group-context";
import { AuthTopBar } from "@/features/auth/adapter/client";

/**
 * Group-scoped layout segment.
 *
 * Every `/g/[groupSlug]/...` route shares this layout. It exposes the
 * URL's slug via :func:`useActiveGroupSlug` to the rest of the app —
 * including the api-client middleware, which uses it to substitute
 * ``{group_slug}`` in outgoing REST URLs.
 *
 * In multi-tenant mode the layout gates the whole `/g/<slug>` subtree: a
 * signed-out request is sent to `/sign-in`, preserving the deep link as the
 * post-login destination, before any child page renders. The gate lives here
 * rather than in the proxy because the proxy must not answer non-document
 * requests with a 404, which is what fails the deployment healthcheck. This is
 * therefore what protects a direct link to a run. In single-tenant mode the
 * check is skipped.
 *
 * The layout also mounts the adapter's top bar. Choosing another group there
 * navigates to ``/g/<otherSlug>/runs``: the URL stays the source of truth, and
 * the next request's credential is checked against the new slug.
 */
export default async function GroupLayout({
  params,
  children,
}: {
  params: Promise<{ groupSlug: string | string[] }>;
  children: ReactNode;
}) {
  const { configured, userId } = await readSession();
  if (configured && userId === null) {
    redirect("/sign-in");
  }
  const resolved = await params;
  const raw = resolved.groupSlug;
  const groupSlug = Array.isArray(raw) ? (raw[0] ?? "") : raw;
  return (
    <GroupProvider slug={groupSlug}>
      <AuthTopBar />
      {children}
    </GroupProvider>
  );
}
