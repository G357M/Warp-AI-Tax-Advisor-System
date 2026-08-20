/**
 * useQuery Hook - Manage query state and API calls
 */

import { useState, useCallback } from 'react';
import axios from 'axios';
import { apiClient, QueryRequest, QueryResponse } from '@/lib/api';
import { authFetch, isLoggedIn } from '@/lib/auth';

/**
 * Errors reach the UI as a kind, never as a raw exception message:
 * the component maps each kind to localized, human copy.
 */
export type QueryErrorKind = 'network' | 'rate_limit' | 'auth' | 'service';

interface UseQueryState {
  data: QueryResponse | null;
  loading: boolean;
  error: QueryErrorKind | null;
}

interface UseQueryReturn extends UseQueryState {
  submitQuery: (query: string, language: 'ka' | 'ru' | 'en') => Promise<void>;
  reset: () => void;
}

class QueryHttpError extends Error {
  constructor(readonly status: number) {
    super(`Query request failed with status ${status}`);
  }
}

function classifyError(err: unknown): QueryErrorKind {
  if (err instanceof QueryHttpError) {
    if (err.status === 429) return 'rate_limit';
    if (err.status === 401) return 'auth';
    return 'service';
  }
  if (axios.isAxiosError(err)) {
    // Timeout means our side is slow, not that the user is offline.
    if (err.code === 'ECONNABORTED') return 'service';
    if (!err.response) return 'network';
    if (err.response.status === 429) return 'rate_limit';
    if (err.response.status === 401) return 'auth';
  }
  return 'service';
}

export function useQuery(): UseQueryReturn {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [state, setState] = useState<UseQueryState>({
    data: null,
    loading: false,
    error: null,
  });

  const submitQuery = useCallback(async (query: string, language: 'ka' | 'ru' | 'en') => {
    // Reset error state
    setState(prev => ({ ...prev, error: null, loading: true }));

    try {
      const request: QueryRequest = {
        query,
        language,
      };
      let response: QueryResponse;
      if (isLoggedIn()) {
        if (conversationId) request.conversation_id = conversationId;
        const res = await authFetch('/api/v1/query', {
          method: 'POST',
          body: JSON.stringify(request),
        });
        if (!res.ok) {
          throw new QueryHttpError(res.status);
        }
        response = await res.json();
        setConversationId(response.conversation_id ?? null);
      } else {
        const result = await apiClient.post<QueryResponse>('/query', request);
        response = result.data;
        setConversationId(null);
      }

      setState({
        data: response,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState({
        data: null,
        loading: false,
        error: classifyError(err),
      });
    }
  }, [conversationId]);

  const reset = useCallback(() => {
    setState({
      data: null,
      loading: false,
      error: null,
    });
    setConversationId(null);
  }, []);

  return {
    ...state,
    submitQuery,
    reset,
  };
}
