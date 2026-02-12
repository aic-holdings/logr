"use server"

import { getServerLogrClient, type SemanticSearchResponse, type SearchResult } from "@/lib/logr"

export async function searchLogs(
  query: string,
  service?: string,
  limit?: number
): Promise<SemanticSearchResponse> {
  const client = getServerLogrClient()
  return await client.semanticSearch(query, { service, limit })
}

export async function findSimilarLogs(
  logId: string,
  limit: number = 10
): Promise<SearchResult[]> {
  const client = getServerLogrClient()
  return await client.findSimilar(logId, limit)
}
