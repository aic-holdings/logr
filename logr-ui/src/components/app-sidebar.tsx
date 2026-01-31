"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Activity,
  AlertTriangle,
  BarChart3,
  FileText,
  Home,
  Key,
  LogOut,
  Search,
  Settings,
  Share2,
} from "lucide-react"

import { signOutAction } from "@/app/actions/auth"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"

const navigationGroups = [
  {
    label: null,
    items: [
      { name: "Dashboard", href: "/", icon: Home },
    ],
  },
  {
    label: "Logs",
    items: [
      { name: "Explorer", href: "/logs", icon: FileText },
      { name: "Search", href: "/search", icon: Search },
      { name: "Traces", href: "/traces", icon: Share2 },
    ],
  },
  {
    label: "Analysis",
    items: [
      { name: "Anomalies", href: "/anomalies", icon: AlertTriangle },
      { name: "Stats", href: "/stats", icon: BarChart3 },
    ],
  },
  {
    label: "Admin",
    items: [
      { name: "API Keys", href: "/admin", icon: Key },
    ],
  },
]

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <div className="flex h-full w-64 flex-col border-r bg-sidebar">
      {/* Header */}
      <div className="flex h-14 items-center border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Activity className="h-5 w-5" />
          </div>
          <span className="text-lg">Logr</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-2">
        {navigationGroups.map((group, groupIndex) => (
          <div key={groupIndex} className={cn(groupIndex > 0 && "mt-4")}>
            {group.label && (
              <div className="px-3 py-2">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {group.label}
                </h3>
              </div>
            )}
            <div className="space-y-1">
              {group.items.map((item) => {
                const isActive = pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href))
                return (
                  <Button
                    key={item.name}
                    variant={isActive ? "secondary" : "ghost"}
                    className={cn(
                      "w-full justify-start gap-2",
                      isActive && "bg-sidebar-accent text-sidebar-accent-foreground"
                    )}
                    asChild
                  >
                    <Link href={item.href}>
                      <item.icon className="h-4 w-4" />
                      {item.name}
                    </Link>
                  </Button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <Separator />
      <div className="p-2 space-y-1">
        <Button variant="ghost" className="w-full justify-start gap-2" asChild>
          <Link href="/settings">
            <Settings className="h-4 w-4" />
            Settings
          </Link>
        </Button>
        <form action={signOutAction}>
          <Button
            type="submit"
            variant="ghost"
            className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
            Sign Out
          </Button>
        </form>
      </div>
    </div>
  )
}
