"use client"

import { useState, useTransition } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Share2, Loader2, Clock, Server, ChevronDown, ChevronRight } from "lucide-react"
import { type Span, type LogEntry, type TraceResponse, type TraceSpansResponse } from "@/lib/logr"
import { formatDate, formatDuration, cn } from "@/lib/utils"
import { lookupTrace } from "./actions"

const SERVICE_COLORS = [
  "bg-blue-400 dark:bg-blue-600",
  "bg-green-400 dark:bg-green-600",
  "bg-purple-400 dark:bg-purple-600",
  "bg-orange-400 dark:bg-orange-600",
  "bg-pink-400 dark:bg-pink-600",
  "bg-teal-400 dark:bg-teal-600",
  "bg-yellow-400 dark:bg-yellow-600",
  "bg-red-400 dark:bg-red-600",
]

function getServiceColor(service: string, services: string[]): string {
  const idx = services.indexOf(service)
  return SERVICE_COLORS[idx % SERVICE_COLORS.length]
}

function SpanBar({
  span,
  traceStart,
  traceDuration,
  depth,
  services,
  expanded,
  onToggle,
  hasChildren,
}: {
  span: Span
  traceStart: number
  traceDuration: number
  depth: number
  services: string[]
  expanded: boolean
  onToggle: () => void
  hasChildren: boolean
}) {
  const spanStart = new Date(span.start_time).getTime()
  const spanDuration = span.duration_ms ?? 0
  const leftPct = traceDuration > 0 ? ((spanStart - traceStart) / traceDuration) * 100 : 0
  const widthPct = traceDuration > 0 ? Math.max((spanDuration / traceDuration) * 100, 0.5) : 100
  const color = getServiceColor(span.service, services)

  return (
    <div className="group">
      <div
        className="flex items-center gap-2 py-1.5 hover:bg-muted/30 cursor-pointer"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={onToggle}
      >
        {hasChildren ? (
          <button className="text-muted-foreground w-4 shrink-0">
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className="text-xs font-medium w-24 shrink-0 truncate">{span.service}</span>
        <span className="text-xs text-muted-foreground w-32 shrink-0 truncate">{span.operation}</span>
        <div className="flex-1 h-5 relative">
          <div
            className={cn("absolute h-full rounded-sm", color, span.status === "error" && "ring-2 ring-red-500")}
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
            title={`${span.operation} (${spanDuration.toFixed(0)}ms)`}
          />
        </div>
        <span className="text-xs text-muted-foreground w-16 text-right shrink-0">
          {spanDuration > 0 ? formatDuration(spanDuration) : "-"}
        </span>
        {span.status === "error" && (
          <span className="text-xs bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 px-1 rounded shrink-0">
            ERR
          </span>
        )}
      </div>
      {expanded && (
        <div className="pl-16 pb-2 text-xs space-y-1" style={{ paddingLeft: `${depth * 20 + 52}px` }}>
          <div className="text-muted-foreground">
            <span>Kind: {span.kind}</span>
            <span className="ml-4">Span ID: <code>{span.span_id}</code></span>
          </div>
          {span.status_message && (
            <div className="text-red-500">{span.status_message}</div>
          )}
          {Object.keys(span.attributes || {}).length > 0 && (
            <pre className="bg-muted p-2 rounded text-xs overflow-x-auto">
              {JSON.stringify(span.attributes, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

interface SpanNode {
  span: Span
  children: SpanNode[]
}

function buildTree(spans: Span[]): SpanNode[] {
  const bySpanId = new Map<string, SpanNode>()
  const roots: SpanNode[] = []

  for (const span of spans) {
    bySpanId.set(span.span_id, { span, children: [] })
  }

  for (const span of spans) {
    const node = bySpanId.get(span.span_id)!
    if (span.parent_span_id && bySpanId.has(span.parent_span_id)) {
      bySpanId.get(span.parent_span_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

function flattenTree(nodes: SpanNode[], depth: number = 0): { span: Span; depth: number; hasChildren: boolean }[] {
  const result: { span: Span; depth: number; hasChildren: boolean }[] = []
  for (const node of nodes) {
    result.push({ span: node.span, depth, hasChildren: node.children.length > 0 })
    result.push(...flattenTree(node.children, depth + 1))
  }
  return result
}

export function TracesClient() {
  const [traceId, setTraceId] = useState("")
  const [traceData, setTraceData] = useState<{
    logs: TraceResponse | null
    spans: TraceSpansResponse | null
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const [expandedSpans, setExpandedSpans] = useState<Set<string>>(new Set())

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!traceId.trim()) return

    setError(null)
    setExpandedSpans(new Set())
    startTransition(async () => {
      const result = await lookupTrace(traceId.trim())
      if (result.error) {
        setError(result.error)
        setTraceData(null)
      } else {
        setTraceData(result)
      }
    })
  }

  function toggleSpan(spanId: string) {
    setExpandedSpans((prev) => {
      const next = new Set(prev)
      if (next.has(spanId)) {
        next.delete(spanId)
      } else {
        next.add(spanId)
      }
      return next
    })
  }

  const spans = traceData?.spans?.spans ?? []
  const logs = traceData?.logs?.logs ?? []
  const services = traceData?.spans?.services ?? traceData?.logs?.services ?? []
  const totalDuration = traceData?.spans?.total_duration_ms ?? traceData?.logs?.total_duration_ms

  const traceStart = spans.length > 0
    ? Math.min(...spans.map((s) => new Date(s.start_time).getTime()))
    : 0
  const traceDurationMs = totalDuration ?? (spans.length > 0
    ? Math.max(...spans.map((s) => new Date(s.start_time).getTime() + (s.duration_ms ?? 0))) - traceStart
    : 0)

  const flatSpans = flattenTree(buildTree(spans))

  return (
    <div className="space-y-6">
      {/* Lookup Form */}
      <Card>
        <CardHeader>
          <CardTitle>Look Up Trace</CardTitle>
          <CardDescription>Enter a trace ID to view the full request flow</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex gap-4">
            <Input
              placeholder="Enter trace_id..."
              value={traceId}
              onChange={(e) => setTraceId(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" disabled={isPending || !traceId.trim()}>
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Share2 className="h-4 w-4 mr-2" />
              )}
              View Trace
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="py-6 text-center text-red-500">
            {error}
          </CardContent>
        </Card>
      )}

      {/* Trace Summary */}
      {traceData && !error && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Share2 className="h-5 w-5" />
              Trace: <code className="text-sm font-normal">{traceId}</code>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Duration</span>
                <p className="font-bold">
                  {totalDuration != null ? formatDuration(totalDuration) : "N/A"}
                </p>
              </div>
              <div>
                <span className="text-muted-foreground">Spans</span>
                <p className="font-bold">{spans.length}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Logs</span>
                <p className="font-bold">{logs.length}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Services</span>
                <div className="flex gap-1 flex-wrap mt-1">
                  {services.map((s) => (
                    <span
                      key={s}
                      className={cn("px-2 py-0.5 rounded text-xs text-white", getServiceColor(s, services))}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Span Waterfall */}
      {spans.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Span Waterfall
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {/* Header */}
              <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground bg-muted/50">
                <span className="w-4 shrink-0" />
                <span className="w-24 shrink-0">Service</span>
                <span className="w-32 shrink-0">Operation</span>
                <span className="flex-1">Timeline</span>
                <span className="w-16 text-right shrink-0">Duration</span>
                <span className="w-8 shrink-0" />
              </div>
              {/* Spans */}
              {flatSpans.map(({ span, depth, hasChildren }) => (
                <SpanBar
                  key={span.id}
                  span={span}
                  traceStart={traceStart}
                  traceDuration={traceDurationMs}
                  depth={depth}
                  services={services}
                  expanded={expandedSpans.has(span.span_id)}
                  onToggle={() => toggleSpan(span.span_id)}
                  hasChildren={hasChildren}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Linked Logs */}
      {logs.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <Server className="h-4 w-4" />
              Trace Logs ({logs.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {logs.map((log: LogEntry) => (
                <div key={log.id} className="p-3 hover:bg-muted/30">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-36 shrink-0">
                      {formatDate(log.timestamp)}
                    </span>
                    <span className={cn(
                      "px-2 py-0.5 rounded text-xs font-medium",
                      log.level === "error" || log.level === "fatal"
                        ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                        : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                    )}>
                      {log.level.toUpperCase()}
                    </span>
                    <span className="text-sm font-medium w-24 shrink-0">{log.service}</span>
                    <span className="text-sm flex-1 truncate">{log.message}</span>
                    {log.duration_ms != null && (
                      <span className="text-xs text-muted-foreground shrink-0">
                        {formatDuration(log.duration_ms)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!traceData && !error && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <Share2 className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p>Enter a trace ID above to view the distributed trace.</p>
              <p className="text-sm mt-1">
                You can find trace IDs in the Log Explorer or by searching logs.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
