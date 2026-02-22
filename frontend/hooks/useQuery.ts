/**
 * useQuery Hook - Manage query state and API calls
 */

import { useState, useCallback } from 'react';
import { apiClient, QueryRequest, QueryResponse } from '@/lib/api';

interface UseQueryState {
  data: QueryResponse | null;
  loading: boolean;
  error: string | null;
}

interface UseQueryReturn extends UseQueryState {
  submitQuery: (query: string, language: 'ka' | 'ru' | 'en') => Promise<void>;
  reset: () => void;
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
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      
      setState({
        data: null,
        loading: false,
        error: errorMessage,
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
