"use client";

import { useCallback, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";

export interface PendingEdit {
  messageId: string;
  newText: string;
}

export function useFork(runId: string) {
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
      modelOverrides,
    }: {
      targetMessageId: string;
      model: string;
      provider: string;
      modelOverrides?: Record<string, { model: string; provider: string }> | null;
    }) => {
      const edits = [...pendingEdits.values()].map(e => ({
        message_id: e.messageId,
        new_text: e.newText,
      }));

      const { data, error } = await api.POST("/api/runs/{run_id}/fork", {
        params: { path: { run_id: runId } },
        body: {
          target_message_id: targetMessageId,
          message_edits: edits,
          model,
          provider,
          model_overrides: modelOverrides ?? null,
        },
      });
      if (error) {
        throw new Error("Failed to create fork");
      }
      return data;
    },
    onSuccess: data => {
      clearEdits();
      window.location.href = `/runs/${data.fork_run_id}`;
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
