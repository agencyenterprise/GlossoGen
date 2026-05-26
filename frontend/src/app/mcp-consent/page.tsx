"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

/**
 * Clerk-gated consent page for MCP OAuth flows.
 *
 * The backend's ``SchmidtOAuthProvider.authorize()`` parks the request and
 * redirects the user-agent here with ``?request_id=<uuid>``. Clerk's
 * ``<SignedOut><RedirectToSignIn/></SignedOut>`` forces sign-in first.
 * The user picks (or confirms) which organization to authorize; on
 * approve the page POSTs to ``/mcp/consent/approve`` with a fresh Clerk
 * JWT and follows the returned ``redirect_url`` (the OAuth client's
 * callback) so the CLI receives its code + state.
 *
 * The body is loaded via ``next/dynamic`` with ``ssr: false`` so Clerk
 * hooks never execute server-side, and wrapped in ``<Suspense>`` because
 * ``useSearchParams()`` forces the page out of static prerendering.
 */
const ConsentClient = dynamic(() => import("./consent-client").then(mod => mod.ConsentClient), {
  ssr: false,
});

function ConsentEntry() {
  const searchParams = useSearchParams();
  const requestId = searchParams.get("request_id");

  if (requestId === null || requestId === "") {
    return (
      <>
        <h1 className="mb-2 text-2xl font-bold tracking-tight">Invalid consent link</h1>
        <p className="text-sm text-muted-foreground">
          The consent URL is missing its <code>request_id</code> parameter.
        </p>
      </>
    );
  }

  return (
    <>
      <h1 className="mb-4 text-2xl font-bold tracking-tight">Authorize MCP access</h1>
      <ConsentClient requestId={requestId} />
    </>
  );
}

export default function McpConsentPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 py-10">
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        <ConsentEntry />
      </Suspense>
    </main>
  );
}
