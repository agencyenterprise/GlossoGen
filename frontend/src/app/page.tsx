import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { LOCAL_GROUP_SLUG } from "@/shared/lib/local-tenant";

/**
 * Root redirect.
 *
 * In local mode (no Clerk) we send the user to ``/g/local/runs``. In
 * Clerk mode we use the session's last active organization slug; if the
 * user has none yet, Clerk's middleware will have already redirected
 * them to ``/sign-in``.
 */
export default async function Home() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    redirect(`/g/${LOCAL_GROUP_SLUG}/runs`);
  }
  const { sessionClaims } = await auth();
  const orgSlug =
    typeof sessionClaims?.org_slug === "string" && sessionClaims.org_slug.length > 0
      ? sessionClaims.org_slug
      : null;
  if (orgSlug === null) {
    redirect("/sign-in");
  }
  redirect(`/g/${orgSlug}/runs`);
}
