import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../api/http';
import { queryClient } from '../api/queryClient';
import type { ChatMessage, ChatSession, Plan } from '../api/types';

export function useSessions() {
  return useQuery({
    queryKey: ['chat', 'sessions'],
    queryFn: () => api.get<{ items: ChatSession[] }>('/chat/sessions'),
  });
}

export interface CreateSessionInput { title?: string; source_id?: string | null }

export function useEnsureSession() {
  return useMutation({
    mutationFn: (input?: CreateSessionInput) =>
      api.post<ChatSession>('/chat/sessions', input ? { ...input } : undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chat', 'sessions'] }),
  });
}

export function useMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['chat', sessionId, 'messages'],
    queryFn: () => api.get<{ items: ChatMessage[] }>(`/chat/sessions/${sessionId}/messages`),
    enabled: !!sessionId,
  });
}

export function useSendMessage(sessionId: string | undefined) {
  return useMutation({
    mutationFn: (content: string) =>
      api.post<{ reply: string; plan: Plan }>(`/chat/sessions/${sessionId}/messages`, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', sessionId, 'messages'] });
      queryClient.invalidateQueries({ queryKey: ['traces'] });
    },
  });
}

export function useConfirmPlan(sessionId: string | undefined) {
  return useMutation({
    mutationFn: (planId: string) => api.post<Plan>(`/plans/${planId}/confirm`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', sessionId, 'messages'] });
      queryClient.invalidateQueries({ queryKey: ['traces'] });
    },
  });
}

export function useCancelPlan(sessionId: string | undefined) {
  return useMutation({
    mutationFn: (planId: string) => api.post<Plan>(`/plans/${planId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chat', sessionId, 'messages'] }),
  });
}
