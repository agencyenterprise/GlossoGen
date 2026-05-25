"use client";

import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";

/**
 * Top bar shown inside every ``/g/[groupSlug]/...`` route.
 *
 * In Clerk mode this renders Clerk's ``<OrganizationSwitcher>`` and
 * ``<UserButton>``. Switching an org navigates the user to
 * ``/g/<newSlug>/runs`` so the URL stays the source of truth (no
 * ``setActive`` call required — the next request's JWT-membership check
 * accepts the new URL slug as long as the user is a member). Renders
 * nothing in local mode.
 */
export function GroupTopBar() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return null;
  }
  return (
    <header className="flex items-center justify-end gap-3 border-b border-border bg-background px-4 py-2">
      <OrganizationSwitcher
        hidePersonal
        afterSelectOrganizationUrl={org => `/g/${org.slug}/runs`}
        afterCreateOrganizationUrl={org => `/g/${org.slug}/runs`}
        afterLeaveOrganizationUrl="/"
      />
      <UserButton />
    </header>
  );
}
