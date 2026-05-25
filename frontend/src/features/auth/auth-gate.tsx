"use client";

import type { ReactNode } from "react";

/**
 * Auth gate stub.
 *
 * The new identity middleware accepts every request automatically when the
 * backend is in local mode (no CLERK_SECRET_KEY set), so the frontend no
 * longer needs to prompt for a shared password. Step 8 of the multi-tenancy
 * rollout replaces this with the Clerk provider + sign-in flow and deletes
 * this file outright.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
