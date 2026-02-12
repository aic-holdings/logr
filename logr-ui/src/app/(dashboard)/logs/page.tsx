import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient } from "@/lib/logr"
import { LogsClient } from "./client"

async function getInitialData() {
  try {
    const client = getServerLogrClient()
    const [logsResult, servicesResult] = await Promise.all([
      client.getLogs({ limit: 50 }),
      client.getServices(),
    ])
    return {
      logs: logsResult.logs,
      services: servicesResult,
    }
  } catch {
    return { logs: [], services: [] }
  }
}

export default async function LogsPage() {
  const { logs, services } = await getInitialData()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Log Explorer</h1>
        <p className="text-muted-foreground">
          Search and filter logs across all services
        </p>
      </div>

      <LogsClient initialLogs={logs} services={services} />
    </div>
  )
}
