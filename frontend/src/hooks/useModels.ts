import { useQuery } from '@tanstack/react-query';
import { getApiBaseUrl } from '../lib/api-config';

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number | null;
  input_price_per_mtok: number | null;
  output_price_per_mtok: number | null;
  provider: string;
}

/**
 * Fetch available models for a given provider from the model browser API.
 * Returns cached data for 5 minutes (matching backend cache TTL).
 * Disabled when provider is null (no fetch until provider is selected).
 */
export function useModels(provider: string | null) {
  return useQuery<ModelInfo[]>({
    queryKey: ['models', provider],
    queryFn: async () => {
      const baseUrl = getApiBaseUrl();
      const resp = await fetch(`${baseUrl}/api/models/?provider=${provider}`);
      if (!resp.ok) throw new Error(`Failed to fetch models: ${resp.status}`);
      return resp.json();
    },
    enabled: !!provider,
    staleTime: 5 * 60 * 1000, // 5 minutes -- matches backend cache TTL
  });
}
