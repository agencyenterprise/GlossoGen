"use client";

import { useState } from "react";
import { approveMcpConsent } from "./approve";
import { describeConsentDestination, type ConsentDestination } from "./consent-destination";
import { useConsentRequest } from "./use-consent-request";

/**
 * What the visitor confirms before an OAuth client receives its authorization code.
 *
 * Any client can register and send a signed-in user here, so the panel names the
 * client and the callback the code is sent to, and offers Approve only once it has
 * both. The copy names glossogen concepts (runs, groups), so it is platform-owned.
 * The auth adapter has already settled which group is being authorized and passes it
 * in.
 */
export function ConsentPanel({
  requestId,
  groupName,
  groupSlug,
}: {
  requestId: string;
  groupName: string;
  groupSlug: string;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const consentRequest = useConsentRequest(requestId);

  async function approve() {
    setSubmitting(true);
    setError(null);
    try {
      window.location.href = await approveMcpConsent({ requestId });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  if (consentRequest.isPending) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (consentRequest.isError) {
    return (
      <p className="rounded bg-red-50 p-3 text-sm text-red-800">
        {consentRequest.error.message.replace(/\.$/, "")}. Start the sign-in again from your client.
      </p>
    );
  }

  let destination: ConsentDestination;
  try {
    destination = describeConsentDestination(consentRequest.data.redirect_uri);
  } catch (err) {
    return (
      <p className="rounded bg-red-50 p-3 text-sm text-red-800">
        {err instanceof Error ? err.message : String(err)}
      </p>
    );
  }
  const clientName = consentRequest.data.client_name ?? "An unnamed client";
  const scopes = consentRequest.data.scopes;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        <strong>{clientName}</strong> is requesting access to your <strong>{groupName}</strong>{" "}
        group (<code>{groupSlug}</code>). It will be able to read and write simulation runs in that
        group.
        {scopes.length > 0 ? (
          <>
            {" "}
            Scopes: <code>{scopes.join(", ")}</code>.
          </>
        ) : null}
      </p>
      <div className="rounded border border-gray-300 p-3 text-sm">
        <ConsentDestinationNote destination={destination} />
        <p className="mt-1 break-all text-xs text-muted-foreground">
          {consentRequest.data.redirect_uri}
        </p>
        {destination.kind === "loopback" ? null : (
          <p className="mt-2 font-medium text-amber-800">
            Approve only if you started this sign-in yourself from a client you trust. The client
            chooses its own name, so check where the authorization goes.
          </p>
        )}
      </div>
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
          {submitting ? "Approving…" : `Approve for ${groupSlug}`}
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

/** Says who receives the authorization code once the request is approved. */
function ConsentDestinationNote({ destination }: { destination: ConsentDestination }) {
  if (destination.kind === "loopback") {
    return (
      <p>
        Approving sends the authorization to <code>{destination.origin}</code>, an application on
        this computer.
      </p>
    );
  }
  if (destination.kind === "web") {
    return (
      <p>
        Approving sends the authorization to <code>{destination.origin}</code>. Whoever runs that
        site will hold access to this group.
      </p>
    );
  }
  return (
    <p>
      Approving sends the authorization to whichever app opens <code>{destination.scheme}</code>{" "}
      links. Some such links hand the authorization on to a web page.
    </p>
  );
}
