"use client";

import { SignUpView } from "@/features/auth/adapter/client";

/** Sign-up route. Same shape as the sign-in page. */
export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950">
      <SignUpView />
    </div>
  );
}
