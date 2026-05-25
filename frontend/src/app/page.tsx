import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { LOCAL_GROUP_SLUG } from "@/shared/lib/local-tenant";

/**
 * Root redirect.
 *
 * In local mode (no Clerk) we send the user to ``/g/local/runs``. In
 * Clerk mode there are three cases:
 *
 * 1. Not signed in: Clerk's proxy already gates routes. Falling through
 *    to ``/sign-in`` is safe — it shows the sign-in card.
 * 2. Signed in with an active org: redirect to that org's runs list.
 * 3. Signed in with no active org (e.g. just after SSO, or after
 *    deleting the previously active org): send them to ``/select-org``
 *    where ``<OrganizationList>`` lets them pick or create one. Going
 *    to ``/sign-in`` here would loop (Clerk sees the live session and
 *    bounces back to ``/``).
 */
export default async function Home() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    redirect(`/g/${LOCAL_GROUP_SLUG}/runs`);
  }
  const { userId, sessionClaims } = await auth();
  if (userId === null || userId === undefined) {
    redirect("/sign-in");
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
