import { getServerLogrClient } from "@/lib/logr"
import { StatsClient } from "./client"

async function getInitialStats() {
  try {
    const client = getServerLogrClient()
    const [stats, errors] = await Promise.all([
      client.getStats({ hours: 24 }),
      client.getGroupedErrors({ hours: 24 }),
    ])
    return { stats, errors }
  } catch {
    return null
  }
}

export default async function StatsPage() {
  const data = await getInitialStats()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Statistics</h1>
        <p className="text-muted-foreground">
          Log volume, error rates, latency, and LLM usage
        </p>
      </div>
      <StatsClient initialData={data} />
    </div>
  )
}
