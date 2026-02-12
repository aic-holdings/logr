/**
 * Logr API client for the UI
 */

const LOGR_API_URL = process.env.NEXT_PUBLIC_LOGR_API_URL || "https://logr.jettaintelligence.com"

export interface LogEntry {
  id: string
  service: string
  level: string
  message: string
  context: Record<string, unknown>
  environment: string
  host: string | null
  version: string | null
  trace_id: string | null
  span_id: string | null
  parent_span_id: string | null
  request_id: string | null
  user_id: string | null
  session_id: string | null
  timestamp: string
  duration_ms: number | null
  created_at: string
  model: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  error_type: string | null
  error_message: string | null
  events: LogEvent[]
}

export interface LogEvent {
  id: string
  event_type: string
  content: string | null
  content_type: string
  sequence: number
  duration_ms: number | null
  timestamp: string
}

export interface Span {
  id: string
  trace_id: string
  span_id: string
  parent_span_id: string | null
  service: string
  operation: string
  kind: string
  start_time: string
  end_time: string | null
  duration_ms: number | null
  status: string
  status_message: string | null
  attributes: Record<string, unknown>
}

export interface LogQueryParams {
  service?: string
  level?: string
  trace_id?: string
  since?: string
  until?: string
  has_error?: boolean
  model?: string
  min_duration_ms?: number
  limit?: number
  offset?: number
}

export interface ServiceAccount {
  id: string
  name: string
  description: string | null
  created_at: string
}

export interface APIKey {
  id: string
  name: string
  key_prefix: string
  can_write: boolean
  can_read: boolean
  created_at: string
  last_used_at: string | null
  revoked: boolean
}

export interface RetentionStats {
  total_logs: number
  logs_to_delete: number
  oldest_log: string | null
  retention_days: number
}

export interface ErrorSpike {
  service: string
  current_rate: number
  baseline_rate: number
  increase: number
}

export interface LatencyAnomaly {
  service: string
  current_avg: number
  baseline_avg: number
  increase: number
}

export interface NewErrorType {
  error_type: string
  service: string
  first_seen: string
  count: number
}

export interface AnomaliesResponse {
  time_window_hours: number
  anomalies: Anomaly[]
  current_period: PeriodStats
  previous_period: PeriodStats
}

export interface Anomaly {
  type: string
  severity: string
  message: string
  previous?: number
  current?: number
  error_types?: string[]
}

export interface PeriodStats {
  total: number
  errors: number
  avg_latency_ms: number | null
}

export interface AdminStats {
  logs: number
  events: number
  spans: number
  service_accounts: number
  api_keys: number
  retention_days: number
  date_range: {
    oldest: string | null
    newest: string | null
  }
}

// Search types
export interface SearchResult {
  id: string
  service: string
  level: string
  message: string
  timestamp: string
  similarity: number
  trace_id: string | null
  error_type: string | null
  signals?: Record<string, number> | null
}

export interface SemanticSearchResponse {
  query: string
  results: SearchResult[]
  total: number
  signals_used?: Record<string, boolean> | null
  search_mode?: string | null
}

// Stats types
export interface ModelStats {
  count: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface LatencyStats {
  avg_ms: number | null
  min_ms: number | null
  max_ms: number | null
  p50_ms: number | null
  p95_ms: number | null
  p99_ms: number | null
}

export interface StatsResponse {
  time_window_hours: number
  total: number
  by_level: Record<string, number>
  by_service: Record<string, number>
  by_model: Record<string, ModelStats>
  by_error: Record<string, number>
  latency: LatencyStats
}

// Grouped errors types
export interface ErrorGroup {
  error_type: string | null
  message_prefix: string
  count: number
  first_seen: string
  last_seen: string
  services: string[]
}

export interface GroupedErrorsResponse {
  time_window_hours: number
  total_groups: number
  groups: ErrorGroup[]
}

// Trace types
export interface TraceResponse {
  trace_id: string
  logs: LogEntry[]
  span_count: number
  services: string[]
  start_time: string
  end_time: string
  total_duration_ms: number | null
}

export interface TraceSpansResponse {
  trace_id: string
  spans: Span[]
  tree: SpanNode[]
  services: string[]
  total_duration_ms: number | null
}

export interface SpanNode {
  span: Span
  children: SpanNode[]
}

// Embedding pipeline status
export interface EmbeddingStatus {
  enabled: boolean
  running: boolean
  daily_count: number
  daily_cap: number
  daily_date: string | null
  total_embedded: number
  total_errors: number
  last_run: string | null
  config: {
    poll_interval_seconds: number
    batch_size: number
    min_message_length: number
    excluded_services: string[]
    excluded_levels: string[]
    embedding_model: string
  }
}

class LogrClient {
  private apiKey: string

  constructor(apiKey: string) {
    this.apiKey = apiKey
  }

  private async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(`${LOGR_API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
        ...options.headers,
      },
    })

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(error.detail || "API request failed")
    }

    return res.json()
  }

  // Logs
  async getLogs(params: LogQueryParams = {}): Promise<{ logs: LogEntry[]; total: number; page: number; page_size: number; has_more: boolean }> {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value))
    })
    return this.fetch(`/v1/logs?${searchParams}`)
  }

  async getLog(id: string): Promise<LogEntry> {
    return this.fetch(`/v1/logs/${id}`)
  }

  async getLogsByTrace(traceId: string): Promise<TraceResponse> {
    return this.fetch(`/v1/logs/trace/${traceId}`)
  }

  async getServices(): Promise<string[]> {
    return this.fetch("/v1/logs/services")
  }

  async getModels(): Promise<string[]> {
    return this.fetch("/v1/logs/models")
  }

  async getStats(params: { service?: string; hours?: number } = {}): Promise<StatsResponse> {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value))
    })
    return this.fetch(`/v1/logs/stats?${searchParams}`)
  }

  // Spans
  async getSpans(params: { trace_id?: string; service?: string } = {}): Promise<{ spans: Span[] }> {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value))
    })
    return this.fetch(`/v1/spans?${searchParams}`)
  }

  async getTrace(traceId: string): Promise<TraceSpansResponse> {
    return this.fetch(`/v1/spans/trace/${traceId}`)
  }

  // Search
  async semanticSearch(query: string, params: { service?: string; limit?: number } = {}): Promise<SemanticSearchResponse> {
    return this.fetch("/v1/search/semantic", {
      method: "POST",
      body: JSON.stringify({ query, ...params }),
    })
  }

  async findSimilar(logId: string, limit: number = 10): Promise<SearchResult[]> {
    return this.fetch("/v1/search/similar", {
      method: "POST",
      body: JSON.stringify({ log_id: logId, limit }),
    })
  }

  async detectAnomalies(hours: number = 24): Promise<AnomaliesResponse> {
    return this.fetch(`/v1/search/anomalies?hours=${hours}`)
  }

  async getGroupedErrors(params: { hours?: number; service?: string; min_count?: number } = {}): Promise<GroupedErrorsResponse> {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value))
    })
    return this.fetch(`/v1/search/errors/grouped?${searchParams}`)
  }

  // Admin (requires master key)
  async getServiceAccounts(): Promise<{ service_accounts: ServiceAccount[] }> {
    return this.fetch("/v1/admin/service-accounts")
  }

  async createServiceAccount(name: string, description?: string): Promise<{ service_account_id: string; api_key: string }> {
    return this.fetch("/v1/admin/service-accounts", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    })
  }

  async getAPIKeys(): Promise<{ keys: APIKey[] }> {
    return this.fetch("/v1/admin/keys")
  }

  async revokeAPIKey(keyId: string): Promise<{ message: string }> {
    return this.fetch(`/v1/admin/keys/${keyId}`, { method: "DELETE" })
  }

  async getAdminStats(): Promise<AdminStats> {
    return this.fetch("/v1/admin/stats")
  }

  async getRetentionStats(): Promise<RetentionStats> {
    return this.fetch("/v1/admin/retention/stats")
  }

  async getEmbeddingStatus(): Promise<EmbeddingStatus> {
    return this.fetch("/v1/admin/embeddings/status")
  }
}

export function createLogrClient(apiKey: string): LogrClient {
  return new LogrClient(apiKey)
}

// Server-side client using master key
export function getServerLogrClient(): LogrClient {
  const masterKey = process.env.LOGR_MASTER_KEY
  if (!masterKey) {
    throw new Error("LOGR_MASTER_KEY is not set")
  }
  return new LogrClient(masterKey)
}
