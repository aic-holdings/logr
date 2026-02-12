import { getServerLogrClient } from "@/lib/logr"
import { SearchClient } from "./client"

async function getServices(): Promise<string[]> {
  try {
    const client = getServerLogrClient()
    return await client.getServices()
  } catch {
    return []
  }
}

export default async function SearchPage() {
  const services = await getServices()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Semantic Search</h1>
        <p className="text-muted-foreground">
          Search logs by meaning using natural language
        </p>
      </div>
      <SearchClient services={services} />
    </div>
  )
}
