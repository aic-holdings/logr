"use client"

import { useState, useTransition } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Search, Sparkles, Loader2 } from "lucide-react"
import { type SearchResult, type SemanticSearchResponse } from "@/lib/logr"
import { formatDate, cn } from "@/lib/utils"
import { searchLogs, findSimilarLogs } from "./actions"

function LogLevelBadge({ level }: { level: string }) {
  return (
    <span className={cn(
      "px-2 py-0.5 rounded text-xs font-medium",
      level === "error" || level === "fatal"
        ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
        : level === "warn"
          ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
          : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    )}>
      {level.toUpperCase()}
    </span>
  )
}

function SimilarityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-muted rounded overflow-hidden">
        <div
          className={cn(
            "h-full rounded",
            pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-gray-400"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-10">{pct}%</span>
    </div>
  )
}

const SIGNAL_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  bm25: { label: "BM25", bg: "bg-blue-100 dark:bg-blue-900", text: "text-blue-700 dark:text-blue-300" },
  vector: { label: "Vector", bg: "bg-purple-100 dark:bg-purple-900", text: "text-purple-700 dark:text-purple-300" },
  heuristic: { label: "Heuristic", bg: "bg-amber-100 dark:bg-amber-900", text: "text-amber-700 dark:text-amber-300" },
  text_fallback: { label: "Text", bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-700 dark:text-gray-300" },
}

function SignalIndicators({ signals }: { signals?: Record<string, number> | null }) {
  if (!signals) return null
  return (
    <div className="flex items-center gap-1">
      {Object.keys(signals).map((key) => {
        const config = SIGNAL_CONFIG[key]
        if (!config) return null
        return (
          <span
            key={key}
            className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium", config.bg, config.text)}
          >
            {config.label}
          </span>
        )
      })}
    </div>
  )
}

function SignalSummary({ response }: { response: SemanticSearchResponse }) {
  if (!response.signals_used) return null
  return (
    <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground flex-wrap">
      <span>Signals:</span>
      {Object.entries(response.signals_used).map(([key, active]) => {
        if (!active) return null
        const config = SIGNAL_CONFIG[key]
        if (!config) return null
        return (
          <span key={key} className={cn("px-1.5 py-0.5 rounded", config.bg, config.text)}>
            {config.label}
          </span>
        )
      })}
      {response.search_mode && (
        <span className="opacity-70">({response.search_mode})</span>
      )}
    </div>
  )
}

interface SearchClientProps {
  services: string[]
}

export function SearchClient({ services }: SearchClientProps) {
  const [query, setQuery] = useState("")
  const [selectedService, setSelectedService] = useState<string>("")
  const [results, setResults] = useState<SemanticSearchResponse | null>(null)
  const [similarResults, setSimilarResults] = useState<{ logId: string; results: SearchResult[] } | null>(null)
  const [isPending, startTransition] = useTransition()
  const [isSimilarPending, startSimilarTransition] = useTransition()

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return

    setSimilarResults(null)
    startTransition(async () => {
      try {
        const data = await searchLogs(
          query.trim(),
          selectedService || undefined,
          20
        )
        setResults(data)
      } catch {
        setResults({ query: query.trim(), results: [], total: 0 })
      }
    })
  }

  function handleFindSimilar(logId: string) {
    startSimilarTransition(async () => {
      try {
        const data = await findSimilarLogs(logId, 10)
        setSimilarResults({ logId, results: data })
      } catch {
        setSimilarResults({ logId, results: [] })
      }
    })
  }

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex gap-4 flex-wrap">
            <div className="flex-1 min-w-[300px] relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Describe what you're looking for..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-9"
              />
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
            <Button type="submit" disabled={isPending || !query.trim()}>
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Sparkles className="h-4 w-4 mr-2" />
              )}
              Search
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {results && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">
              Results ({results.total})
            </CardTitle>
            <CardDescription>
              Showing matches for &ldquo;{results.query}&rdquo;
            </CardDescription>
            <SignalSummary response={results} />
          </CardHeader>
          <CardContent className="p-0">
            {results.results.length > 0 ? (
              <div className="divide-y">
                {results.results.map((result) => (
                  <div key={result.id} className="p-4 hover:bg-muted/30">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <LogLevelBadge level={result.level} />
                          <span className="text-sm font-medium">{result.service}</span>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(result.timestamp)}
                          </span>
                        </div>
                        <p className="text-sm">{result.message}</p>
                        {result.trace_id && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Trace: <span className="font-mono">{result.trace_id}</span>
                          </p>
                        )}
                        {result.error_type && (
                          <p className="text-xs text-red-500 mt-1">
                            {result.error_type}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <SimilarityBar score={result.similarity} />
                        <SignalIndicators signals={result.signals} />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleFindSimilar(result.id)}
                          disabled={isSimilarPending}
                          className="text-xs"
                        >
                          Find Similar
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-muted-foreground">
                No matching logs found
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Similar Results */}
      {similarResults && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">
              Similar Logs ({similarResults.results.length})
            </CardTitle>
            <CardDescription>
              Logs similar to selected entry
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {similarResults.results.length > 0 ? (
              <div className="divide-y">
                {similarResults.results.map((result) => (
                  <div key={result.id} className="p-4 hover:bg-muted/30">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <LogLevelBadge level={result.level} />
                          <span className="text-sm font-medium">{result.service}</span>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(result.timestamp)}
                          </span>
                        </div>
                        <p className="text-sm">{result.message}</p>
                      </div>
                      <SimilarityBar score={result.similarity} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center text-muted-foreground">
                No similar logs found
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!results && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <Sparkles className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p>Enter a natural language query to search logs by meaning.</p>
              <p className="text-sm mt-1">
                Examples: &ldquo;database connection timeout&rdquo;, &ldquo;user authentication failed&rdquo;, &ldquo;slow API response&rdquo;
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
