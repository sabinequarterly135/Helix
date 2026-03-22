import { useLocation } from 'react-router-dom'
import { Link } from 'react-router-dom'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import React from 'react'
import { useTranslation } from 'react-i18next'

const LABEL_KEYS: Record<string, string> = {
  prompts: 'breadcrumbs.prompts',
  template: 'breadcrumbs.template',
  dataset: 'breadcrumbs.dataset',
  config: 'breadcrumbs.config',
  evolution: 'breadcrumbs.evolution',
  history: 'breadcrumbs.history',
  playground: 'breadcrumbs.playground',
  settings: 'breadcrumbs.settings',
  wizard: 'breadcrumbs.wizard',
}

interface BreadcrumbEntry {
  label: string
  path: string
  isLast: boolean
}

export function AppBreadcrumbs() {
  const location = useLocation()
  const { t } = useTranslation()

  const crumbs = buildBreadcrumbs(location.pathname, t)

  if (crumbs.length === 0) return null

  return (
    <Breadcrumb className="mb-4">
      <BreadcrumbList>
        {crumbs.map((crumb, index) => (
          <React.Fragment key={crumb.path}>
            {index > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {crumb.isLast ? (
                <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link to={crumb.path}>{crumb.label}</Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function buildBreadcrumbs(pathname: string, t: (key: string, options?: Record<string, unknown>) => string): BreadcrumbEntry[] {
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length < 2) return []

  const crumbs: BreadcrumbEntry[] = []
  let currentPath = ''

  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i]
    currentPath += `/${segment}`
    const isLast = i === segments.length - 1

    if (LABEL_KEYS[segment]) {
      crumbs.push({ label: t(LABEL_KEYS[segment]), path: currentPath, isLast })
    } else if (segments[i - 1] === 'history') {
      // This is a runId under history
      crumbs.push({ label: t('breadcrumbs.runNumber', { number: segment }), path: currentPath, isLast })
    } else {
      // This is a promptId
      crumbs.push({ label: segment, path: currentPath, isLast })
    }
  }

  return crumbs
}
