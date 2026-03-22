import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { AppBreadcrumbs } from './Breadcrumbs'

export default function AppShell() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          <AppBreadcrumbs />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
