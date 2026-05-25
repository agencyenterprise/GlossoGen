import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js middleware.
 *
 * When `CLERK_SECRET_KEY` is set, delegate to Clerk's middleware so every
 * route gets a session attached (and Clerk handles redirects to /sign-in).
 * In local mode (no Clerk env vars) this is a no-op pass-through so the
 * dev server runs without any Clerk config.
 */
function isClerkConfigured(): boolean {
  return Boolean(process.env.CLERK_SECRET_KEY && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

const _clerkMiddleware = isClerkConfigured() ? clerkMiddleware() : null;

export default function middleware(request: NextRequest, event: import("next/server").NextFetchEvent) {
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
