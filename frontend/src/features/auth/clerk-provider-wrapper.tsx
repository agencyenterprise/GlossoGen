"use client";

import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

/**
 * Conditional Clerk provider.
 *
 * The publishable key arrives as a prop from the root layout, which reads it
 * from the runtime environment. Passing it explicitly — rather than letting
 * `<ClerkProvider>` pick up an inlined `NEXT_PUBLIC_*` value — is what keeps
 * one compiled image usable across environments.
 *
 * A null key means single-tenant local mode: children render directly and the
 * backend's identity middleware short-circuits every request to the synthetic
 * `local` group.
 */
export function ClerkProviderWrapper({
  publishableKey,
  children,
}: {
  publishableKey: string | null;
  children: ReactNode;
}) {
  if (publishableKey === null) {
    return <>{children}</>;
  }
  return <ClerkProvider publishableKey={publishableKey}>{children}</ClerkProvider>;
}
