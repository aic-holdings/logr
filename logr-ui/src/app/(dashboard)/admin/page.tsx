import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getServerLogrClient, type ServiceAccount, type APIKey } from "@/lib/logr"
import { Key, Users, Shield } from "lucide-react"

async function getAdminData() {
  try {
    const client = getServerLogrClient()
    const [accountsResult, keysResult, statsResult] = await Promise.all([
      client.getServiceAccounts(),
      client.getAPIKeys(),
      client.getRetentionStats(),
    ])
    return {
      accounts: accountsResult.service_accounts,
      keys: keysResult.keys,
      retention: statsResult,
    }
  } catch {
    return { accounts: [], keys: [], retention: null }
  }
}

export default async function AdminPage() {
  const { accounts, keys, retention } = await getAdminData()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin</h1>
        <p className="text-muted-foreground">
          Manage service accounts, API keys, and retention
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Service Accounts</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{accounts.length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">API Keys</CardTitle>
            <Key className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{keys.length}</div>
            <p className="text-xs text-muted-foreground">
              {keys.filter(k => !k.revoked).length} active
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Retention</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{retention?.retention_days ?? 90} days</div>
            <p className="text-xs text-muted-foreground">
              {retention?.logs_to_delete?.toLocaleString() ?? 0} logs pending cleanup
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Service Accounts */}
      <Card>
        <CardHeader>
          <CardTitle>Service Accounts</CardTitle>
          <CardDescription>
            Services configured to send logs
          </CardDescription>
        </CardHeader>
        <CardContent>
          {accounts.length > 0 ? (
            <div className="divide-y">
              {accounts.map((account: ServiceAccount) => (
                <div key={account.id} className="flex items-center justify-between py-3">
                  <div>
                    <span className="font-medium">{account.name}</span>
                    {account.description && (
                      <p className="text-sm text-muted-foreground">{account.description}</p>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    Created {new Date(account.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No service accounts yet
            </p>
          )}
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <CardTitle>API Keys</CardTitle>
          <CardDescription>
            Authentication keys for services
          </CardDescription>
        </CardHeader>
        <CardContent>
          {keys.length > 0 ? (
            <div className="divide-y">
              {keys.map((key: APIKey) => (
                <div key={key.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <code className="text-sm bg-muted px-2 py-1 rounded">
                      {key.key_prefix}...
                    </code>
                    <span className="font-medium">{key.name}</span>
                    {key.revoked && (
                      <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded">
                        Revoked
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground space-x-4">
                    <span>
                      {key.can_write ? "Write" : ""} {key.can_read ? "Read" : ""}
                    </span>
                    {key.last_used_at && (
                      <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No API keys yet
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
