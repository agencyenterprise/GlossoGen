"use client";

import { SignInView } from "@/features/auth/adapter/client";

/**
 * Sign-in route.
 *
 * A shell: the adapter supplies the form. The `[[...rest]]` catch-all segment
 * stays because a provider's internal flow URLs (verify, callback, second factor)
 * all have to resolve to this page.
 */
export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950">
      <SignInView />
    </div>
  );
}
