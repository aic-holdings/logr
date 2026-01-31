import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient } from "@/lib/logr"

async function getStats() {
  try {
    const client = getServerLogrClient()
    const stats = await client.getAdminStats()
    return stats
  } catch {
    return null
  }
}

export default async function DashboardPage() {
  const stats = await getStats()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Centralized logging and observability for all AIC services
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Logs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.logs?.toLocaleString() ?? "—"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Events</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.events?.toLocaleString() ?? "—"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Spans</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.spans?.toLocaleString() ?? "—"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Services</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.service_accounts ?? "—"}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quick Links</CardTitle>
            <CardDescription>Common actions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <a href="/logs" className="block p-2 rounded-lg hover:bg-muted">
              → Search Logs
            </a>
            <a href="/traces" className="block p-2 rounded-lg hover:bg-muted">
              → View Traces
            </a>
            <a href="/anomalies" className="block p-2 rounded-lg hover:bg-muted">
              → Detect Anomalies
            </a>
            <a href="/admin" className="block p-2 rounded-lg hover:bg-muted">
              → Manage API Keys
            </a>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Info</CardTitle>
            <CardDescription>Database and retention</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Retention Days</span>
              <span>{stats?.retention_days ?? 90}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Oldest Log</span>
              <span>{stats?.date_range?.oldest ? new Date(stats.date_range.oldest).toLocaleDateString() : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Newest Log</span>
              <span>{stats?.date_range?.newest ? new Date(stats.date_range.newest).toLocaleDateString() : "—"}</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
