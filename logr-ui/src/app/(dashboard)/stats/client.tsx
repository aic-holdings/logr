"use client"

import { useState, useTransition } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { BarChart3, AlertTriangle, Clock, Activity } from "lucide-react"
import { type StatsResponse, type GroupedErrorsResponse, type ModelStats } from "@/lib/logr"
import { formatDate } from "@/lib/utils"
import { fetchStats } from "./actions"

const TIME_WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "48h", hours: 48 },
  { label: "7d", hours: 168 },
]

const LEVEL_COLORS: Record<string, string> = {
  debug: "bg-gray-200 dark:bg-gray-700",
  info: "bg-blue-200 dark:bg-blue-700",
  warn: "bg-yellow-200 dark:bg-yellow-700",
  error: "bg-red-200 dark:bg-red-700",
  fatal: "bg-purple-200 dark:bg-purple-700",
}

interface StatsClientProps {
  initialData: { stats: StatsResponse; errors: GroupedErrorsResponse } | null
}

export function StatsClient({ initialData }: StatsClientProps) {
  const [data, setData] = useState(initialData)
  const [selectedHours, setSelectedHours] = useState(24)
  const [isPending, startTransition] = useTransition()

  const stats = data?.stats
  const errors = data?.errors

  function handleTimeChange(hours: number) {
    setSelectedHours(hours)
    startTransition(async () => {
      try {
        const result = await fetchStats(hours)
        setData(result)
      } catch {
        // Keep existing data on error
      }
    })
  }

  const totalLogs = stats?.total ?? 0
  const errorCount = (stats?.by_level?.error ?? 0) + (stats?.by_level?.fatal ?? 0)
  const errorRate = totalLogs > 0 ? (errorCount / totalLogs) * 100 : 0
  const avgLatency = stats?.latency?.avg_ms
  const p95Latency = stats?.latency?.p95_ms

  // Find max for bar chart scaling
  const levelEntries = Object.entries(stats?.by_level ?? {})
  const maxLevelCount = Math.max(...levelEntries.map(([, v]) => v), 1)

  const serviceEntries = Object.entries(stats?.by_service ?? {}).slice(0, 10)
  const maxServiceCount = Math.max(...serviceEntries.map(([, v]) => v), 1)

  const modelEntries = Object.entries(stats?.by_model ?? {}) as [string, ModelStats][]

  return (
    <div className="space-y-6">
      {/* Time Window Selector */}
      <div className="flex gap-2">
        {TIME_WINDOWS.map((tw) => (
          <Button
            key={tw.hours}
            variant={selectedHours === tw.hours ? "default" : "outline"}
            size="sm"
            onClick={() => handleTimeChange(tw.hours)}
            disabled={isPending}
          >
            {tw.label}
          </Button>
        ))}
        {isPending && <span className="text-sm text-muted-foreground self-center ml-2">Loading...</span>}
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Logs</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalLogs.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              Last {selectedHours}h
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Error Rate</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${errorRate > 5 ? "text-red-500" : ""}`}>
              {errorRate.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              {errorCount.toLocaleString()} errors
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Latency</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {avgLatency != null ? `${avgLatency.toFixed(0)}ms` : "N/A"}
            </div>
            <p className="text-xs text-muted-foreground">Mean response time</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">P95 Latency</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {p95Latency != null ? `${p95Latency.toFixed(0)}ms` : "N/A"}
            </div>
            <p className="text-xs text-muted-foreground">95th percentile</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Logs by Level */}
        <Card>
          <CardHeader>
            <CardTitle>Logs by Level</CardTitle>
          </CardHeader>
          <CardContent>
            {levelEntries.length > 0 ? (
              <div className="space-y-3">
                {levelEntries
                  .sort((a, b) => b[1] - a[1])
                  .map(([level, count]) => (
                    <div key={level} className="flex items-center gap-3">
                      <span className="text-sm w-12 text-right font-medium uppercase">{level}</span>
                      <div className="flex-1 h-6 bg-muted rounded overflow-hidden">
                        <div
                          className={`h-full rounded ${LEVEL_COLORS[level] ?? "bg-gray-300"}`}
                          style={{ width: `${(count / maxLevelCount) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground w-16 text-right">
                        {count.toLocaleString()}
                      </span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">No data</p>
            )}
          </CardContent>
        </Card>

        {/* Logs by Service */}
        <Card>
          <CardHeader>
            <CardTitle>Top Services</CardTitle>
          </CardHeader>
          <CardContent>
            {serviceEntries.length > 0 ? (
              <div className="space-y-3">
                {serviceEntries
                  .sort((a, b) => b[1] - a[1])
                  .map(([service, count]) => (
                    <div key={service} className="flex items-center gap-3">
                      <span className="text-sm w-28 truncate text-right font-medium">{service}</span>
                      <div className="flex-1 h-6 bg-muted rounded overflow-hidden">
                        <div
                          className="h-full rounded bg-blue-400 dark:bg-blue-600"
                          style={{ width: `${(count / maxServiceCount) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground w-16 text-right">
                        {count.toLocaleString()}
                      </span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">No data</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* LLM Model Usage */}
      {modelEntries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>LLM Model Usage</CardTitle>
            <CardDescription>Token consumption and cost by model</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-2 font-medium">Model</th>
                    <th className="pb-2 font-medium text-right">Calls</th>
                    <th className="pb-2 font-medium text-right">Tokens In</th>
                    <th className="pb-2 font-medium text-right">Tokens Out</th>
                    <th className="pb-2 font-medium text-right">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {modelEntries
                    .sort((a, b) => b[1].count - a[1].count)
                    .map(([model, ms]) => (
                      <tr key={model} className="border-b last:border-b-0">
                        <td className="py-2 font-mono text-xs">{model}</td>
                        <td className="py-2 text-right">{ms.count.toLocaleString()}</td>
                        <td className="py-2 text-right">{ms.tokens_in.toLocaleString()}</td>
                        <td className="py-2 text-right">{ms.tokens_out.toLocaleString()}</td>
                        <td className="py-2 text-right">${ms.cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Grouped Errors */}
      <Card>
        <CardHeader>
          <CardTitle>Grouped Errors</CardTitle>
          <CardDescription>Recurring error patterns (min 2 occurrences)</CardDescription>
        </CardHeader>
        <CardContent>
          {errors && errors.groups.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-2 font-medium">Error Type</th>
                    <th className="pb-2 font-medium">Message</th>
                    <th className="pb-2 font-medium text-right">Count</th>
                    <th className="pb-2 font-medium">Services</th>
                    <th className="pb-2 font-medium">Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {errors.groups.map((group, i) => (
                    <tr key={i} className="border-b last:border-b-0">
                      <td className="py-2 font-mono text-xs text-red-500">
                        {group.error_type ?? "Unknown"}
                      </td>
                      <td className="py-2 text-xs max-w-xs truncate">
                        {group.message_prefix}
                      </td>
                      <td className="py-2 text-right font-bold">{group.count}</td>
                      <td className="py-2">
                        <div className="flex gap-1 flex-wrap">
                          {group.services.map((s) => (
                            <span key={s} className="text-xs bg-muted px-1 rounded">{s}</span>
                          ))}
                        </div>
                      </td>
                      <td className="py-2 text-xs text-muted-foreground">
                        {formatDate(group.last_seen)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No recurring errors detected
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
