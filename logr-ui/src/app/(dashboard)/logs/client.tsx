"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { LogEntry } from "@/lib/logr"
import { formatDate, formatDuration, truncate, cn } from "@/lib/utils"
import { ChevronDown, ChevronRight, Search } from "lucide-react"

interface LogsClientProps {
  initialLogs: LogEntry[]
  services: string[]
}

function LogLevelBadge({ level }: { level: string }) {
  return (
    <span className={cn(
      "px-2 py-0.5 rounded text-xs font-medium",
      `log-level-${level.toLowerCase()}`
    )}>
      {level.toUpperCase()}
    </span>
  )
}

function LogRow({ log, expanded, onToggle }: { log: LogEntry; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="border-b last:border-b-0">
      <div
        className="flex items-center gap-4 p-3 hover:bg-muted/50 cursor-pointer"
        onClick={onToggle}
      >
        <button className="text-muted-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <span className="text-xs text-muted-foreground w-36 shrink-0">
          {formatDate(log.timestamp)}
        </span>
        <LogLevelBadge level={log.level} />
        <span className="text-sm font-medium w-24 shrink-0">{log.service}</span>
        <span className="text-sm flex-1 truncate">{log.message}</span>
        {log.duration_ms && (
          <span className="text-xs text-muted-foreground">
            {formatDuration(log.duration_ms)}
          </span>
        )}
      </div>
      {expanded && (
        <div className="p-4 bg-muted/30 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {log.trace_id && (
              <div>
                <span className="text-muted-foreground">Trace ID:</span>
                <span className="ml-2 font-mono text-xs">{truncate(log.trace_id, 20)}</span>
              </div>
            )}
            {log.model && (
              <div>
                <span className="text-muted-foreground">Model:</span>
                <span className="ml-2">{log.model}</span>
              </div>
            )}
            {log.tokens_in && (
              <div>
                <span className="text-muted-foreground">Tokens:</span>
                <span className="ml-2">{log.tokens_in} / {log.tokens_out}</span>
              </div>
            )}
            {log.cost_usd && (
              <div>
                <span className="text-muted-foreground">Cost:</span>
                <span className="ml-2">${log.cost_usd.toFixed(4)}</span>
              </div>
            )}
            {log.error_type && (
              <div className="col-span-2">
                <span className="text-muted-foreground">Error:</span>
                <span className="ml-2 text-red-500">{log.error_type}: {log.error_message}</span>
              </div>
            )}
          </div>
          {Object.keys(log.context || {}).length > 0 && (
            <div>
              <span className="text-sm text-muted-foreground">Context:</span>
              <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto">
                {JSON.stringify(log.context, null, 2)}
              </pre>
            </div>
          )}
          {log.events.length > 0 && (
            <div>
              <span className="text-sm text-muted-foreground">Events ({log.events.length}):</span>
              <div className="mt-1 space-y-2">
                {log.events.map((event) => (
                  <div key={event.id} className="p-2 bg-muted rounded">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-medium">{event.event_type}</span>
                      <span className="text-muted-foreground">#{event.sequence}</span>
                    </div>
                    {event.content && (
                      <pre className="mt-1 text-xs whitespace-pre-wrap">
                        {truncate(event.content, 500)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function LogsClient({ initialLogs, services }: LogsClientProps) {
  const [logs, setLogs] = useState(initialLogs)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedService, setSelectedService] = useState<string>("")
  const [selectedLevel, setSelectedLevel] = useState<string>("")
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filteredLogs = logs.filter((log) => {
    if (selectedService && log.service !== selectedService) return false
    if (selectedLevel && log.level !== selectedLevel) return false
    if (searchQuery && !log.message.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex gap-4 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search logs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <select
              className="border rounded-md px-3 py-2 text-sm"
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
            >
              <option value="">All Services</option>
              {services.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              className="border rounded-md px-3 py-2 text-sm"
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value)}
            >
              <option value="">All Levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
              <option value="fatal">Fatal</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Logs List */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">
            Logs ({filteredLogs.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y">
            {filteredLogs.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                No logs found
              </div>
            ) : (
              filteredLogs.map((log) => (
                <LogRow
                  key={log.id}
                  log={log}
                  expanded={expandedId === log.id}
                  onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
                />
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
