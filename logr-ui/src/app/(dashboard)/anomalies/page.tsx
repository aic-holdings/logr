import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient } from "@/lib/logr"
import { AlertTriangle, TrendingUp, Zap } from "lucide-react"

async function getAnomalies() {
  try {
    const client = getServerLogrClient()
    return await client.detectAnomalies(24)
  } catch {
    return null
  }
}

export default async function AnomaliesPage() {
  const anomalies = await getAnomalies()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Anomaly Detection</h1>
        <p className="text-muted-foreground">
          Automatic detection of error spikes, latency changes, and new error types
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Error Spikes</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {anomalies?.error_spikes?.length ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Unusual error rate increases
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Latency Anomalies</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {anomalies?.latency_anomalies?.length ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Slower than normal responses
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">New Error Types</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {anomalies?.new_error_types?.length ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Previously unseen errors
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Error Spikes */}
      <Card>
        <CardHeader>
          <CardTitle>Error Spikes (Last 24h)</CardTitle>
          <CardDescription>
            Services with unusual error rate increases
          </CardDescription>
        </CardHeader>
        <CardContent>
          {anomalies?.error_spikes?.length > 0 ? (
            <div className="space-y-4">
              {anomalies.error_spikes.map((spike: { service: string; current_rate: number; baseline_rate: number; increase: number }, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <div>
                    <span className="font-medium">{spike.service}</span>
                    <p className="text-sm text-muted-foreground">
                      {spike.current_rate.toFixed(1)}% error rate (baseline: {spike.baseline_rate.toFixed(1)}%)
                    </p>
                  </div>
                  <span className="text-red-600 font-bold">
                    +{spike.increase.toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No error spikes detected
            </p>
          )}
        </CardContent>
      </Card>

      {/* New Error Types */}
      <Card>
        <CardHeader>
          <CardTitle>New Error Types</CardTitle>
          <CardDescription>
            Error types seen for the first time
          </CardDescription>
        </CardHeader>
        <CardContent>
          {anomalies?.new_error_types?.length > 0 ? (
            <div className="space-y-2">
              {anomalies.new_error_types.map((error: { error_type: string; service: string; first_seen: string; count: number }, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
                  <div>
                    <span className="font-medium font-mono">{error.error_type}</span>
                    <p className="text-sm text-muted-foreground">
                      in {error.service} • first seen {new Date(error.first_seen).toLocaleString()}
                    </p>
                  </div>
                  <span className="text-muted-foreground">
                    {error.count} occurrences
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No new error types detected
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
