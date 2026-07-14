"use client";

import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";

/**
 * Group controls shown inside every ``/g/[groupSlug]/...`` route.
 *
 * In Clerk mode this renders Clerk's ``<OrganizationSwitcher>`` and
 * ``<UserButton>`` as a floating overlay pinned to the top-right corner, so it
 * doesn't consume a layout row — page content starts at the very top and slides
 * beneath it. Switching an org navigates the user to ``/g/<newSlug>/runs`` so
 * the URL stays the source of truth (no ``setActive`` call required — the next
 * request's JWT-membership check accepts the new URL slug as long as the user
 * is a member). Renders nothing in local mode.
 *
 * The outer wrapper is ``pointer-events-none`` so only the pill itself is
 * clickable; the empty corner around it stays transparent to the page beneath.
 */
export function GroupTopBar() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return null;
  }
  return (
    <div className="pointer-events-none fixed right-3 top-2.5 z-50 flex items-center justify-end">
      <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border/60 bg-background/80 px-2 py-1 shadow-sm backdrop-blur">
        <OrganizationSwitcher
          hidePersonal
          afterSelectOrganizationUrl={org => `/g/${org.slug}/runs`}
          afterCreateOrganizationUrl={org => `/g/${org.slug}/runs`}
          afterLeaveOrganizationUrl="/"
        />
        <UserButton />
      </div>
    </div>
  );
}
