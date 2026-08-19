"use client";

import { useState } from "react";
import { approveMcpConsent } from "./approve";

/**
 * What the visitor confirms before the CLI receives its authorization code.
 *
 * The copy names glossogen concepts (runs, groups), so it is platform-owned. The
 * auth adapter has already settled which group is being authorized and passes it
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

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        The glossogen CLI is requesting access to your <strong>{groupName}</strong> group (
        <code>{groupSlug}</code>). It will be able to read and write simulation runs in that group.
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
