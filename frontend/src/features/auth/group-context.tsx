"use client";

import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { setActiveGroupSlug } from "@/shared/lib/api-client";

/**
 * Active tenant group context.
 *
 * Provides the slug of the group whose runs the user is currently
 * browsing, and mirrors it into ``api-client``'s module-level
 * ``_activeGroupSlug`` so the openapi-fetch middleware can substitute
 * ``{group_slug}`` placeholders in URLs without each call site passing
 * ``params.path.group_slug``.
 *
 * The slug is set from the URL segment in ``/g/[groupSlug]/layout.tsx``.
 * The Clerk JWT proves membership; the URL declares the active group.
 * No ``setActive`` calls — multi-org users can browse multiple groups
 * concurrently in separate tabs.
 */
type GroupContextValue = {
  slug: string;
};

const GroupContext = createContext<GroupContextValue | null>(null);

export function GroupProvider({ slug, children }: { slug: string; children: ReactNode }) {
  const value = useMemo(() => ({ slug }), [slug]);
  // Prime the module-level mirror synchronously during render — before any
  // child effect or query fires — so no request can go out with an
  // unsubstituted `{group_slug}` placeholder. The effect only handles the
  // clear-on-unmount cleanup.
  setActiveGroupSlug(slug);
  useEffect(() => {
    setActiveGroupSlug(slug);
    return () => {
      setActiveGroupSlug(null);
    };
  }, [slug]);
  return <GroupContext.Provider value={value}>{children}</GroupContext.Provider>;
}

export function useActiveGroupSlug(): string {
  const ctx = useContext(GroupContext);
  if (ctx === null) {
    throw new Error("useActiveGroupSlug must be used inside <GroupProvider>");
  }
  return ctx.slug;
}

/**
 * Build a URL path scoped to the active group.
 *
 * `groupPath("/runs/foo")` → `/g/{active-slug}/runs/foo`. Always
 * starts with a slash; the caller passes the suffix without the
 * `/g/[slug]` prefix.
 */
export function useGroupPath(): (suffix: string) => string {
  const slug = useActiveGroupSlug();
  return (suffix: string) => {
    const normalized = suffix.startsWith("/") ? suffix : `/${suffix}`;
    return `/g/${slug}${normalized}`;
  };
}
