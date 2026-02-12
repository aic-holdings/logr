"use server"

import { getServerLogrClient, type TraceResponse, type TraceSpansResponse } from "@/lib/logr"

export async function lookupTrace(traceId: string): Promise<{
  logs: TraceResponse | null
  spans: TraceSpansResponse | null
  error?: string
}> {
  const client = getServerLogrClient()

  try {
    const [logs, spans] = await Promise.allSettled([
      client.getLogsByTrace(traceId),
      client.getTrace(traceId),
    ])

    return {
      logs: logs.status === "fulfilled" ? logs.value : null,
      spans: spans.status === "fulfilled" ? spans.value : null,
      error:
        logs.status === "rejected" && spans.status === "rejected"
          ? "Trace not found"
          : undefined,
    }
  } catch {
    return { logs: null, spans: null, error: "Failed to load trace" }
  }
}
