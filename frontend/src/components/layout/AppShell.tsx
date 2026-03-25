import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { AppBreadcrumbs } from './Breadcrumbs'

export default function AppShell() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-4 focus:bg-primary focus:text-primary-foreground focus:rounded-md focus:m-2"
      >
        Skip to main content
      </a>
      <Sidebar />
      <main id="main-content" className="flex-1 overflow-auto">
        <div className="p-6 md:p-6 p-4">
          <AppBreadcrumbs />
          <Outlet />
        </div>
      </main>
    </div>
  )
}
