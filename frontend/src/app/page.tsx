import { auth } from "@clerk/nextjs/server";
import { LOCAL_GROUP_SLUG } from "@/shared/lib/local-tenant";
import { LandingPage } from "@/features/landing/landing-page";

/**
 * Root route — always the public landing page.
 *
 * The header CTA adapts to auth state instead of redirecting, so a visitor is
 * never bounced to a sign-in or org-picker wall before seeing the landing:
 * - local mode (no Clerk): "Dashboard" → the local workspace.
 * - signed out: "Research team login" → /sign-in.
 * - signed in: "Dashboard" → the active org's runs, or /select-org when no org
 *   is active yet.
 */
export default async function Home() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return <LandingPage appHref={`/g/${LOCAL_GROUP_SLUG}/runs`} appLabel="Dashboard" />;
  }

  const { userId, sessionClaims } = await auth();
  if (userId === null || userId === undefined) {
    return <LandingPage appHref="/sign-in" appLabel="Research team login" />;
  }

  const orgSlug =
    typeof sessionClaims?.org_slug === "string" && sessionClaims.org_slug.length > 0
      ? sessionClaims.org_slug
      : null;
  const appHref = orgSlug === null ? "/select-org" : `/g/${orgSlug}/runs`;
  return <LandingPage appHref={appHref} appLabel="Dashboard" />;
}
