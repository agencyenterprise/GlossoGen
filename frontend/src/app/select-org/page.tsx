"use client";

import { GroupPickerView } from "@/features/auth/adapter/client";

/**
 * Lands signed-in visitors who have no active group yet.
 *
 * Reached from the root route when the session carries no group, which happens
 * after an SSO sign-in or after the previously active group was deleted. The
 * adapter supplies the picker; this page owns the framing and the destination a
 * chosen group leads to.
 */
export default function SelectOrgPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 py-10">
      <h1 className="mb-2 text-2xl font-bold tracking-tight">Choose a study group</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Pick an existing group to continue, or create a new one.
      </p>
      <GroupPickerView hrefForGroup={slug => `/g/${slug}/runs`} />
    </main>
  );
}
