import { LOCAL_GROUP_SLUG } from "@/shared/lib/local-tenant";
import { LandingPage } from "@/features/landing/landing-page";
import { readSession } from "@/features/auth/adapter/server";

/**
 * Root route: always the public landing page.
 *
 * The header CTA adapts to auth state instead of redirecting, so a visitor is
 * never bounced to a sign-in or group-picker wall before seeing the landing:
 * - single-tenant mode: "Dashboard" into the local workspace.
 * - signed out: "Research team login".
 * - signed in: "Dashboard" into the active group's runs, or the picker when no
 *   group is active yet.
 */
export default async function Home() {
  const { configured, userId, activeGroupSlug } = await readSession();
  if (!configured) {
    return <LandingPage appHref={`/g/${LOCAL_GROUP_SLUG}/runs`} appLabel="Dashboard" />;
  }
  if (userId === null) {
    return <LandingPage appHref="/sign-in" appLabel="Research team login" />;
  }
  if (activeGroupSlug === null) {
    return <LandingPage appHref="/select-org" appLabel="Dashboard" />;
  }
  return <LandingPage appHref={`/g/${activeGroupSlug}/runs`} appLabel="Dashboard" />;
}
