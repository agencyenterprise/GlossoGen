"use client";

import { SignIn } from "@clerk/nextjs";

/**
 * Catch-all Clerk sign-in route.
 *
 * Reached only when Clerk is configured (no-op middleware in local mode
 * never sends users here). The `[[...rest]]` segment is required by Clerk
 * so its internal flow URLs (verify, sso-callback, factor-one, etc.) all
 * resolve to this page.
 */
export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950">
      <SignIn />
    </div>
  );
}
