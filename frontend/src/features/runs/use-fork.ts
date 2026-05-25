"use client";

import { useCallback, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
import { useGroupPath } from "@/features/auth/group-context";

export interface PendingEdit {
  messageId: string;
  newText: string;
}

export function useFork(runId: string) {
  const groupPath = useGroupPath();
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [pendingEdits, setPendingEdits] = useState<Map<string, PendingEdit>>(new Map());

  const startEdit = useCallback((messageId: string) => {
    setEditingMessageId(messageId);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingMessageId(null);
  }, []);

  const saveEdit = useCallback((messageId: string, newText: string) => {
    setPendingEdits(prev => {
      const next = new Map(prev);
      next.set(messageId, { messageId, newText });
      return next;
    });
    setEditingMessageId(null);
  }, []);

  const clearEdits = useCallback(() => {
    setPendingEdits(new Map());
    setEditingMessageId(null);
  }, []);

  const forkMutation = useMutation({
    mutationFn: async ({
      targetMessageId,
      model,
      provider,
      knobs,
    }: {
      targetMessageId: string;
      model: string;
      provider: string;
      knobs?: Record<string, unknown> | null;
    }) => {
      const edits = [...pendingEdits.values()].map(e => ({
        message_id: e.messageId,
        new_text: e.newText,
      }));

      const { data, error } = await api.POST(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/fork",
        {
          params: { path: splitRunId(runId) },
          body: {
            target_message_id: targetMessageId,
            message_edits: edits,
            model,
            provider,
            knobs: knobs ?? null,
          },
        }
      );
      if (error) {
        throw new Error("Failed to create fork");
      }
      return data;
    },
    onSuccess: data => {
      clearEdits();
      window.location.href = groupPath(`/runs/${data.fork_run_id}`);
    },
  });

  return {
    editingMessageId,
    pendingEdits,
    startEdit,
    saveEdit,
    cancelEdit,
    clearEdits,
    forkMutation,
  };
}
