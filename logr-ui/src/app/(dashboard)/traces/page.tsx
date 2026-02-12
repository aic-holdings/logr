import { TracesClient } from "./client"

export default function TracesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Trace Viewer</h1>
        <p className="text-muted-foreground">
          Visualize distributed traces across services
        </p>
      </div>
      <TracesClient />
    </div>
  )
}
