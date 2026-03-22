import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { FileText, ChevronLeft, ChevronRight, Wand2, Dna, Settings, Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '\u4E2D\u6587' },
  { value: 'es', label: 'Espa\u00F1ol' },
] as const

function CollapsedLink({ to, label, children }: { to: string; label: string; children: React.ReactNode }) {
  const { pathname } = useLocation()
  const isActive = pathname === to || pathname.startsWith(to + '/')

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <NavLink
          to={to}
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-md transition-colors',
            isActive
              ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
              : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
          )}
        >
          {children}
        </NavLink>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const { t, i18n } = useTranslation()

  const currentLangIndex = LANGUAGES.findIndex((l) => l.value === i18n.language) ?? 0

  function cycleLanguage() {
    const nextIndex = (currentLangIndex + 1) % LANGUAGES.length
    i18n.changeLanguage(LANGUAGES[nextIndex].value)
  }

  const currentLangLabel = LANGUAGES.find((l) => l.value === i18n.language)?.label ?? 'English'

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          'flex flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-in-out',
          collapsed ? 'w-14' : 'w-56'
        )}
      >
        {/* Header */}
        <div className={cn(
          'flex h-14 items-center',
          collapsed ? 'justify-center' : 'px-3'
        )}>
          {!collapsed && (
            <span className="flex items-center gap-2 text-lg font-semibold text-sidebar-foreground truncate">
              <Dna className="h-5 w-5 text-primary shrink-0" />
              Helix
            </span>
          )}
          {collapsed && (
            <Dna className="h-5 w-5 text-primary" />
          )}
        </div>

        {/* Toggle button */}
        <div className={cn('flex', collapsed ? 'justify-center' : 'justify-end px-2')}>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCollapsed(!collapsed)}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
        </div>

        {/* Navigation */}
        <nav className={cn('flex-1 py-2', collapsed ? '' : 'px-2')}>
          <ul className={cn('flex flex-col', collapsed ? 'items-center gap-2' : 'gap-1')}>
            <li>
              {collapsed ? (
                <CollapsedLink to="/prompts" label={t('sidebar.prompts')}>
                  <FileText className="h-5 w-5" />
                </CollapsedLink>
              ) : (
                <NavLink
                  to="/prompts"
                  className={({ isActive }) =>
                    cn(
                      'flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                    )
                  }
                >
                  <FileText className="h-4 w-4" />
                  {t('sidebar.prompts')}
                </NavLink>
              )}
            </li>
            <li>
              {collapsed ? (
                <CollapsedLink to="/wizard" label={t('sidebar.wizard')}>
                  <Wand2 className="h-5 w-5" />
                </CollapsedLink>
              ) : (
                <NavLink
                  to="/wizard"
                  className={({ isActive }) =>
                    cn(
                      'flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                    )
                  }
                >
                  <Wand2 className="h-4 w-4" />
                  {t('sidebar.wizard')}
                </NavLink>
              )}
            </li>
          </ul>
        </nav>

        {/* Bottom section: Language selector + Settings */}
        <div className={cn('pb-3', collapsed ? '' : 'px-2')}>
          <Separator className={cn('mb-2', collapsed && 'mx-auto w-10')} />

          {/* Language selector */}
          <div className={cn('mb-1', collapsed && 'flex justify-center')}>
            {collapsed ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={cycleLanguage}
                    className="flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                  >
                    <Globe className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  {t('sidebar.language')}: {currentLangLabel}
                </TooltipContent>
              </Tooltip>
            ) : (
              <div className="flex h-10 items-center gap-3 rounded-md px-3">
                <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                <Select
                  value={i18n.language}
                  onValueChange={(value) => i18n.changeLanguage(value)}
                >
                  <SelectTrigger className="h-8 flex-1 text-sm border-0 bg-transparent px-0 shadow-none focus:ring-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((lang) => (
                      <SelectItem key={lang.value} value={lang.value}>
                        {lang.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Settings link */}
          <div className={cn(collapsed && 'flex justify-center')}>
            {collapsed ? (
              <CollapsedLink to="/settings" label={t('sidebar.settings')}>
                <Settings className="h-5 w-5" />
              </CollapsedLink>
            ) : (
              <NavLink
                to="/settings"
                className={({ isActive }) =>
                  cn(
                    'flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary/15 text-primary ring-1 ring-primary/30'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                  )
                }
              >
                <Settings className="h-4 w-4" />
                {t('sidebar.settings')}
              </NavLink>
            )}
          </div>
        </div>
      </aside>
    </TooltipProvider>
  )
}
