import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient, type AnomaliesResponse, type Anomaly } from "@/lib/logr"
import { AlertTriangle, TrendingUp, Zap } from "lucide-react"

async function getAnomalies(): Promise<AnomaliesResponse | null> {
  try {
    const client = getServerLogrClient()
    return await client.detectAnomalies(24)
  } catch {
    return null
  }
}

function filterByType(anomalies: Anomaly[], type: string): Anomaly[] {
  return anomalies.filter((a) => a.type === type)
}

export default async function AnomaliesPage() {
  const data = await getAnomalies()
  const anomalies = data?.anomalies ?? []
  const errorSpikes = filterByType(anomalies, "error_rate_spike")
  const latencySpikes = filterByType(anomalies, "latency_spike")
  const newErrors = filterByType(anomalies, "new_error_types")

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
              {errorSpikes.length}
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
              {latencySpikes.length}
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
              {newErrors.length}
            </div>
            <p className="text-xs text-muted-foreground">
              Previously unseen errors
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Period Comparison */}
      {data && (
        <Card>
          <CardHeader>
            <CardTitle>Period Comparison (Last 24h vs Previous 24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Current Total</span>
                <p className="text-lg font-bold">{data.current_period.total}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Current Errors</span>
                <p className="text-lg font-bold text-red-500">{data.current_period.errors}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Avg Latency</span>
                <p className="text-lg font-bold">
                  {data.current_period.avg_latency_ms
                    ? `${data.current_period.avg_latency_ms.toFixed(0)}ms`
                    : "N/A"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Anomaly Details */}
      <Card>
        <CardHeader>
          <CardTitle>Detected Anomalies</CardTitle>
          <CardDescription>
            Issues detected in the last 24 hours
          </CardDescription>
        </CardHeader>
        <CardContent>
          {anomalies.length > 0 ? (
            <div className="space-y-4">
              {anomalies.map((anomaly, i) => (
                <div
                  key={i}
                  className={`flex items-center justify-between p-3 rounded-lg ${
                    anomaly.severity === "high"
                      ? "bg-red-50 dark:bg-red-900/20"
                      : "bg-yellow-50 dark:bg-yellow-900/20"
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        anomaly.severity === "high"
                          ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                          : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                      }`}>
                        {anomaly.severity.toUpperCase()}
                      </span>
                      <span className="font-medium capitalize">
                        {anomaly.type.replace(/_/g, " ")}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {anomaly.message}
                    </p>
                    {anomaly.error_types && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {anomaly.error_types.map((et, j) => (
                          <span key={j} className="text-xs font-mono bg-muted px-1 rounded">
                            {et}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No anomalies detected - all systems normal
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
