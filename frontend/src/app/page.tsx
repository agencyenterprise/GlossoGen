import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { LOCAL_GROUP_SLUG } from "@/shared/lib/local-tenant";
import { LandingPage } from "@/features/landing/landing-page";

/**
 * Root route.
 *
 * Shows the public landing page to first-time visitors. In local mode (no
 * Clerk) the page is always rendered — its secondary CTA opens the app. In
 * Clerk mode, signed-in users are forwarded to their org's runs (or the org
 * picker when no org is active), so only signed-out visitors see the landing.
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
  if (orgSlug === null) {
    redirect("/select-org");
  }
  redirect(`/g/${orgSlug}/runs`);
}
