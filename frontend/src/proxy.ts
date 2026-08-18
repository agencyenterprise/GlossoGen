import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";
import { authProxyHandler } from "@/features/auth/adapter/proxy";

/**
 * Next.js proxy (the file convention formerly known as middleware).
 *
 * Delegates to the auth adapter's handler when one is supplied, so a provider that
 * needs to see every request gets to. With no handler this is a pass-through,
 * which is single-tenant mode.
 *
 * No `auth.protect()`-style gate belongs here: the healthcheck probes `/` without
 * cookies or a browser `Accept` header, and a provider middleware that answers
 * such non-document requests with 404 fails the Railway healthcheck and blocks
 * every deploy. Route gating is server-side instead, in the root `page.tsx` and
 * the `/g/[groupSlug]` layout, which return a 307 the healthcheck accepts.
 *
 * `config.matcher` is a literal here because Next.js reads it statically and
 * rejects a re-exported one, so it cannot move into the adapter.
 */
export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  if (authProxyHandler === null) {
    return NextResponse.next();
  }
  const response = await authProxyHandler(request, event);
  if (response === null || response === undefined) {
    return NextResponse.next();
  }
  return response;
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files.
    "/((?!_next|.*\\..*).*)",
    "/",
  ],
};
