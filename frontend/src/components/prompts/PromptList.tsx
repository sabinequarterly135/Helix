import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { listPromptsApiPromptsGet } from '@/client/sdk.gen'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Search, FileText, Wand2 } from 'lucide-react'
import { PromptCard } from './PromptCard'
import { Link } from 'react-router-dom'

function PromptCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-[180px]" />
        <Skeleton className="h-4 w-[250px]" />
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      </CardContent>
    </Card>
  )
}

export default function PromptList() {
  const [filter, setFilter] = useState('')
  const { t } = useTranslation()

  const { data: prompts, isLoading, error } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => listPromptsApiPromptsGet(),
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder={t('prompts.searchPlaceholder')} className="pl-9" disabled />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <PromptCardSkeleton />
          <PromptCardSkeleton />
          <PromptCardSkeleton />
        </div>
      </div>
    )
  }

  if (error) {
    return <p className="text-destructive">{t('prompts.failedToLoad')}</p>
  }

  const items = prompts?.data ?? []
  const filtered = items.filter(
    (p) =>
      p.id.toLowerCase().includes(filter.toLowerCase()) ||
      p.purpose.toLowerCase().includes(filter.toLowerCase()),
  )

  // Empty state: no prompts at all
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="rounded-xl border-2 border-dashed border-border p-8 text-center max-w-md">
          <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">{t('prompts.noPromptsYet')}</h3>
          <p className="text-sm text-muted-foreground mb-4">
            {t('prompts.noPromptsDescription')}
          </p>
          <Button asChild>
            <Link to="/wizard"><Wand2 className="h-4 w-4 mr-2" />{t('prompts.newPrompt')}</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('prompts.searchPlaceholder')}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button asChild>
          <Link to="/wizard"><Wand2 className="h-4 w-4 mr-2" />{t('prompts.newPrompt')}</Link>
        </Button>
      </div>

      {filtered.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">{t('prompts.noMatch')}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((prompt) => (
            <PromptCard
              key={prompt.id}
              id={prompt.id}
              purpose={prompt.purpose}
              variableCount={prompt.template_variables.length}
              anchorCount={prompt.anchor_variables.length}
            />
          ))}
        </div>
      )}
    </div>
  )
}
