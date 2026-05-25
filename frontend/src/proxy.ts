import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js proxy (the file convention formerly known as middleware).
 *
 * When `CLERK_SECRET_KEY` is set, delegate to Clerk's middleware so every
 * route gets a session attached (and Clerk handles redirects to /sign-in).
 * In local mode (no Clerk env vars) this is a no-op pass-through so the
 * dev server runs without any Clerk config.
 *
 * `organizationSyncOptions.organizationPatterns` tells Clerk to read the
 * group slug from the URL (`/g/<slug>`) and activate that organization on
 * the session for the current request. This is how a user who belongs to
 * multiple orgs can navigate to any of them by URL without first calling
 * `setActive`. If the user is not a member of the URL's org, Clerk leaves
 * the active org unchanged and the backend's `claims.org_slug == url_slug`
 * check then returns 403.
 */
function isClerkConfigured(): boolean {
  return Boolean(process.env.CLERK_SECRET_KEY && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

const _clerkMiddleware = isClerkConfigured()
  ? clerkMiddleware(() => {}, {
      organizationSyncOptions: {
        organizationPatterns: ["/g/:slug", "/g/:slug/(.*)"],
      },
    })
  : null;

export default function middleware(
  request: NextRequest,
  event: import("next/server").NextFetchEvent
) {
  if (_clerkMiddleware === null) {
    return NextResponse.next();
  }
  return _clerkMiddleware(request, event);
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files.
    "/((?!_next|.*\\..*).*)",
    "/",
  ],
};
