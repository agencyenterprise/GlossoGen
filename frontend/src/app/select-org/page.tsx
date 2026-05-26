"use client";

import dynamic from "next/dynamic";

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
 *
 * Loaded via ``next/dynamic`` with ``ssr: false`` so it is never
 * rendered server-side. Required because ``<OrganizationList>`` throws
 * when no live ``<ClerkProvider>`` is in the tree — and during a
 * production build without ``NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`` set as
 * a build arg, ``<ClerkProvider>`` is not mounted.
 */
const OrganizationPicker = dynamic(
  () =>
    import("@clerk/nextjs").then(mod => {
      const { OrganizationList } = mod;
      return {
        default: function OrganizationPickerInner() {
          return (
            <OrganizationList
              hidePersonal
              afterSelectOrganizationUrl={org => `/g/${org.slug}/runs`}
              afterCreateOrganizationUrl={org => `/g/${org.slug}/runs`}
            />
          );
        },
      };
    }),
  { ssr: false }
);

export default function SelectOrgPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 py-10">
      <h1 className="mb-2 text-2xl font-bold tracking-tight">Choose a study group</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Pick an existing organization to continue, or create a new one.
      </p>
      <OrganizationPicker />
    </main>
  );
}
