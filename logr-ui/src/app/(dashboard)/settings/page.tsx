import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient, type EmbeddingStatus } from "@/lib/logr"
import { Settings, Cpu, Globe, Info } from "lucide-react"

const LOGR_API_URL = process.env.NEXT_PUBLIC_LOGR_API_URL || "https://logr.jettaintelligence.com"

async function getSettingsData(): Promise<{
  health: { version: string; status: string; embeddings: boolean } | null
  embedding: EmbeddingStatus | null
}> {
  try {
    const client = getServerLogrClient()
    const [healthRes, embeddingRes] = await Promise.allSettled([
      fetch(`${LOGR_API_URL}/health`).then((r) => r.json()),
      client.getEmbeddingStatus(),
    ])
    return {
      health: healthRes.status === "fulfilled" ? {
        version: healthRes.value.version,
        status: healthRes.value.status,
        embeddings: healthRes.value.features?.embeddings ?? false,
      } : null,
      embedding: embeddingRes.status === "fulfilled" ? embeddingRes.value : null,
    }
  } catch {
    return { health: null, embedding: null }
  }
}

export default async function SettingsPage() {
  const { health, embedding } = await getSettingsData()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          API connection info and system status
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* API Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              API Connection
            </CardTitle>
            <CardDescription>Logr API endpoint details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">API URL</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">{LOGR_API_URL}</code>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <span className={`font-medium ${health?.status === "healthy" ? "text-green-500" : "text-red-500"}`}>
                {health?.status ?? "Unknown"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Version</span>
              <span>{health?.version ?? "Unknown"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Health</span>
              <a
                href={`${LOGR_API_URL}/health`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline text-xs"
              >
                /health
              </a>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">API Docs</span>
              <a
                href={`${LOGR_API_URL}/docs`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline text-xs"
              >
                /docs
              </a>
            </div>
          </CardContent>
        </Card>

        {/* Embedding Pipeline */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5" />
              Embedding Pipeline
            </CardTitle>
            <CardDescription>Semantic search embedding status</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {embedding ? (
              <>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <span className={`font-medium ${embedding.running ? "text-green-500" : "text-yellow-500"}`}>
                    {embedding.running ? "Running" : embedding.enabled ? "Stopped" : "Disabled"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Today</span>
                  <span>{embedding.daily_count.toLocaleString()} / {embedding.daily_cap.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total Embedded</span>
                  <span>{embedding.total_embedded.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Errors</span>
                  <span className={embedding.total_errors > 0 ? "text-red-500" : ""}>
                    {embedding.total_errors}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Model</span>
                  <code className="text-xs bg-muted px-2 py-1 rounded">{embedding.config.embedding_model}</code>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Batch Size</span>
                  <span>{embedding.config.batch_size}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Poll Interval</span>
                  <span>{embedding.config.poll_interval_seconds}s</span>
                </div>
                {embedding.last_run && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last Run</span>
                    <span className="text-xs">{new Date(embedding.last_run).toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Excluded</span>
                  <div className="flex gap-1">
                    {embedding.config.excluded_services.map((s) => (
                      <code key={s} className="text-xs bg-muted px-1 rounded">{s}</code>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground text-center py-4">
                Unable to load embedding status
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* About */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            About Logr
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <p>
            Logr is a centralized structured logging service for AI-powered analysis.
            It provides structured logging, distributed tracing, LLM operation tracking,
            semantic search, and anomaly detection.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="font-medium text-foreground">Features:</span> Structured Logging, Distributed Tracing, LLM Tracking, Semantic Search, Anomaly Detection
            </div>
            <div>
              <span className="font-medium text-foreground">Stack:</span> FastAPI, PostgreSQL, pgvector, Next.js
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
