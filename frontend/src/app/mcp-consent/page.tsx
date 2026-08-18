"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ConsentGate } from "@/features/auth/adapter/client";
import { ConsentPanel } from "@/features/mcp-consent/consent-panel";

/**
 * Consent page for MCP OAuth flows.
 *
 * The backend parks the authorization request and redirects here with
 * `?request_id=<id>`. The adapter's gate signs the visitor in and settles which
 * group they are authorizing; the panel then confirms and posts back to the
 * backend, which mints the code and returns the OAuth client's callback URL.
 *
 * Wrapped in `<Suspense>` because `useSearchParams()` forces the page out of
 * static prerendering.
 */
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
      <ConsentGate requestId={requestId}>
        {identity => (
          <ConsentPanel
            requestId={requestId}
            groupName={identity.groupName}
            groupSlug={identity.groupSlug}
          />
        )}
      </ConsentGate>
    </>
  );
}

export default function McpConsentPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-10">
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        <ConsentEntry />
      </Suspense>
    </main>
  );
}
