"use client";

import { OrganizationList } from "@clerk/nextjs";

/**
 * Lands signed-in users who don't have an active organization yet.
 *
 * After SSO sign-in or after deleting the previously active org, the
 * Clerk session has no ``org_slug`` and the root redirect (``app/page.tsx``)
 * sends the user here. ``<OrganizationList>`` lists the user's existing
 * memberships, lets them create a new org, and on selection it both
 * calls ``setActive`` and follows ``afterSelectOrganizationUrl`` /
 * ``afterCreateOrganizationUrl`` — landing the user on
 * ``/g/<slug>/runs``.
 */
export default function SelectOrgPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 py-10">
      <h1 className="mb-2 text-2xl font-bold tracking-tight">Choose a study group</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Pick an existing organization to continue, or create a new one.
      </p>
      <OrganizationList
        hidePersonal
        afterSelectOrganizationUrl={org => `/g/${org.slug}/runs`}
        afterCreateOrganizationUrl={org => `/g/${org.slug}/runs`}
      />
    </main>
  );
}
