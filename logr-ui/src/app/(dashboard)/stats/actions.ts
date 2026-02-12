"use server"

import { getServerLogrClient, type StatsResponse, type GroupedErrorsResponse } from "@/lib/logr"

export async function fetchStats(
  hours: number,
  service?: string
): Promise<{ stats: StatsResponse; errors: GroupedErrorsResponse }> {
  const client = getServerLogrClient()
  const [stats, errors] = await Promise.all([
    client.getStats({ hours, service }),
    client.getGroupedErrors({ hours, service }),
  ])
  return { stats, errors }
}
