export interface Memory {
  id: string;
  content: string;
  namespace: string;
  memory_type: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  tags?: string[];
}

export interface MemorySearchResult {
  results: Memory[];
  query: string;
}

export interface MemoryListResponse {
  memories: Memory[];
  total: number;
}

export interface Namespace {
  name: string;
  count: number;
}

export interface Stats {
  namespace_count: number;
  total_memories: number;
  attachments: number;
  plugin_count: number;
}

export interface HealthStatus {
  status: string;
  version: string;
  uptime_seconds: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  size?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AuditEntry {
  timestamp: string;
  action: string;
  details: string;
  user_id?: string;
  namespace?: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
  total: number;
}

export interface Plugin {
  name: string;
  version: string;
  enabled: boolean;
  description?: string;
}

export interface StreamInfo {
  [key: string]: {
    consumers: number;
    length: number;
    last_entry_id?: string;
  };
}
