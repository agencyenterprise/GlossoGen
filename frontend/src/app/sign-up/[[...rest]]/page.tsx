"use client";

import { SignUp } from "@clerk/nextjs";

/**
 * Catch-all Clerk sign-up route. Same shape as the sign-in page above.
 */
export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950">
      <SignUp />
    </div>
  );
}
