/**
 * useQuery Hook - Manage query state and API calls
 */

import { useState, useCallback } from 'react';
import axios from 'axios';
import { apiClient, QueryRequest, QueryResponse } from '@/lib/api';

/**
 * Errors reach the UI as a kind, never as a raw exception message:
 * the component maps each kind to localized, human copy.
 */
export type QueryErrorKind = 'network' | 'rate_limit' | 'service';

interface UseQueryState {
  data: QueryResponse | null;
  loading: boolean;
  error: QueryErrorKind | null;
}

interface UseQueryReturn extends UseQueryState {
  submitQuery: (query: string, language: 'ka' | 'ru' | 'en') => Promise<void>;
  reset: () => void;
}

function classifyError(err: unknown): QueryErrorKind {
  if (axios.isAxiosError(err)) {
    // Timeout means our side is slow, not that the user is offline.
    if (err.code === 'ECONNABORTED') return 'service';
    if (!err.response) return 'network';
    if (err.response.status === 429) return 'rate_limit';
  }
  return 'service';
}

export function useQuery(): UseQueryReturn {
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

      const { data: response } = await apiClient.post<QueryResponse>('/query', request);

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
  }, []);

  const reset = useCallback(() => {
    setState({
      data: null,
      loading: false,
      error: null,
    });
  }, []);

  return {
    ...state,
    submitQuery,
    reset,
  };
}
