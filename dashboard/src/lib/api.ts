import type {
  HealthStatus,
  Stats,
  MemoryListResponse,
  Memory,
  MemorySearchResult,
  GraphData,
  AuditResponse,
  Plugin,
  StreamInfo,
  Namespace,
} from '@/types/api';

const BASE = '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthStatus>('/health'),

  stats: () => request<Stats>('/stats'),

  namespaces: () =>
    request<{ namespaces: Namespace[] }>('/namespaces').then((r) => r.namespaces),

  memories: (params?: { namespace?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.namespace) q.set('namespace', params.namespace);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return request<MemoryListResponse>(`/memories${qs ? `?${qs}` : ''}`);
  },

  memory: (id: string) => request<Memory>(`/memories/${id}`),

  createMemory: (data: { content: string; namespace?: string; memory_type?: string }) =>
    request<{ created: boolean; result: unknown }>('/memories', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteMemory: (id: string) =>
    request<{ deleted: boolean; result: unknown }>(`/memories/${id}`, {
      method: 'DELETE',
    }),

  search: (query: string) =>
    request<MemorySearchResult>(`/search?q=${encodeURIComponent(query)}`),

  graph: () => request<GraphData>('/graph'),

  audit: (limit = 50) => request<AuditResponse>(`/audit?limit=${limit}`),

  plugins: () => request<{ plugins: Plugin[] }>('/plugins').then((r) => r.plugins),

  streams: () => request<{ streams: StreamInfo }>('/streams').then((r) => r.streams),
};
