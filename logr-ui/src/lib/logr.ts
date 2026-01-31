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
  async getLogs(params: LogQueryParams = {}): Promise<{ logs: LogEntry[]; total: number }> {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.set(key, String(value))
    })
    return this.fetch(`/v1/logs?${searchParams}`)
  }

  async getLog(id: string): Promise<LogEntry> {
    return this.fetch(`/v1/logs/${id}`)
  }

  async getLogsByTrace(traceId: string): Promise<{ logs: LogEntry[] }> {
    return this.fetch(`/v1/logs/trace/${traceId}`)
  }

  async getServices(): Promise<{ services: string[] }> {
    return this.fetch("/v1/logs/services")
  }

  async getModels(): Promise<{ models: string[] }> {
    return this.fetch("/v1/logs/models")
  }

  async getStats(params: { service?: string; hours?: number } = {}): Promise<Record<string, unknown>> {
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

  async getTrace(traceId: string): Promise<{ trace_id: string; spans: Span[] }> {
    return this.fetch(`/v1/spans/trace/${traceId}`)
  }

  // Search
  async semanticSearch(query: string, params: { service?: string; limit?: number } = {}): Promise<{ results: LogEntry[] }> {
    return this.fetch("/v1/search/semantic", {
      method: "POST",
      body: JSON.stringify({ query, ...params }),
    })
  }

  async findSimilar(logId: string, limit: number = 10): Promise<{ similar: LogEntry[] }> {
    return this.fetch("/v1/search/similar", {
      method: "POST",
      body: JSON.stringify({ log_id: logId, limit }),
    })
  }

  async detectAnomalies(hours: number = 24): Promise<Record<string, unknown>> {
    return this.fetch(`/v1/search/anomalies?hours=${hours}`)
  }

  async getGroupedErrors(params: { hours?: number; service?: string } = {}): Promise<Record<string, unknown>> {
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

  async getAdminStats(): Promise<Record<string, unknown>> {
    return this.fetch("/v1/admin/stats")
  }

  async getRetentionStats(): Promise<Record<string, unknown>> {
    return this.fetch("/v1/admin/retention/stats")
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
