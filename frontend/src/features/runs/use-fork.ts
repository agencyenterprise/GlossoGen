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

  const removeEdit = useCallback((messageId: string) => {
    setPendingEdits(prev => {
      const next = new Map(prev);
      next.delete(messageId);
      return next;
    });
  }, []);

  const clearEdits = useCallback(() => {
    setPendingEdits(new Map());
    setEditingMessageId(null);
  }, []);

  const forkMutation = useMutation({
    mutationFn: async ({ targetMessageId }: { targetMessageId: string }) => {
      const edits = [...pendingEdits.values()].map(e => ({
        message_id: e.messageId,
        new_text: e.newText,
      }));

      const { data, error } = await api.POST("/api/runs/{run_id}/fork", {
        params: { path: { run_id: runId } },
        body: {
          target_message_id: targetMessageId,
          message_edits: edits,
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
    removeEdit,
    clearEdits,
    forkMutation,
  };
}
