import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function TracesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Trace Viewer</h1>
        <p className="text-muted-foreground">
          Visualize distributed traces across services
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Look Up Trace</CardTitle>
          <CardDescription>
            Enter a trace ID to view the full request flow
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex gap-4">
            <Input
              placeholder="Enter trace_id..."
              className="flex-1"
            />
            <Button type="submit">View Trace</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Traces</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-center py-8">
            Enter a trace ID above or browse logs to find traces
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
