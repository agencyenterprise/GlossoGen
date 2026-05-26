"use client";

import { OrganizationList, RedirectToSignIn, useAuth, useOrganization } from "@clerk/nextjs";
import { useState } from "react";

/**
 * Client-only body of the MCP consent page.
 *
 * Split out so the parent page can lazy-load it via ``next/dynamic`` with
 * ``ssr: false`` — required because Clerk hooks throw when no live
 * ``<ClerkProvider>`` is in the tree during a build without
 * ``NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY``.
 */
export function ConsentClient({ requestId }: { requestId: string }) {
  const { isLoaded: authLoaded, isSignedIn } = useAuth();

  if (!authLoaded) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (!isSignedIn) {
    return <RedirectToSignIn redirectUrl={`/mcp-consent?request_id=${requestId}`} />;
  }
  return <ConsentBody requestId={requestId} />;
}

function ConsentBody({ requestId }: { requestId: string }) {
  const { isLoaded: orgLoaded, organization } = useOrganization();
  const { getToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!orgLoaded) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (organization === null || organization === undefined) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm">Pick which organization the CLI should be authorized for:</p>
        <OrganizationList
          hidePersonal
          afterSelectOrganizationUrl={`/mcp-consent?request_id=${requestId}`}
          afterCreateOrganizationUrl={`/mcp-consent?request_id=${requestId}`}
        />
      </div>
    );
  }

  async function approve() {
    setSubmitting(true);
    setError(null);
    try {
      const token = await getToken();
      if (token === null) {
        throw new Error("No Clerk token available");
      }
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
      // eslint-disable-next-line no-restricted-globals -- /mcp/consent/approve is not in the typed OpenAPI surface
      const response = await fetch(`${apiUrl}/mcp/consent/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ request_id: requestId }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Backend rejected approval (${response.status}): ${detail}`);
      }
      const data = (await response.json()) as { redirect_url: string };
      window.location.href = data.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        The schmidt CLI is requesting access to your <strong>{organization.name}</strong>{" "}
        organization (<code>{organization.slug}</code>). It will be able to read and write
        simulation runs in that group.
      </p>
      {error !== null ? (
        <p className="rounded bg-red-50 p-3 text-sm text-red-800">{error}</p>
      ) : null}
      <div className="flex gap-3">
        <button
          type="button"
          className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:bg-gray-400"
          onClick={() => {
            void approve();
          }}
          disabled={submitting}
        >
          {submitting ? "Approving…" : `Approve for ${organization.slug}`}
        </button>
        <button
          type="button"
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
          onClick={() => {
            window.history.back();
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
