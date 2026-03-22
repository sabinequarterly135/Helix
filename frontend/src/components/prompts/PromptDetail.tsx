import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { getPromptApiPromptsPromptIdGet } from '@/client/sdk.gen'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

interface PromptDetailProps {
  promptId: string
}

interface VariableDefinition {
  name: string
  var_type?: string
  description?: string | null
  is_anchor?: boolean
  items_schema?: VariableDefinition[] | null
}

function PromptDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <Skeleton className="h-7 w-[200px]" />
          <Skeleton className="h-4 w-[350px]" />
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <Skeleton className="h-[200px] w-full" />
        </CardContent>
      </Card>
    </div>
  )
}

function TypeBadge({ varType, hasItems }: { varType?: string; hasItems?: boolean }) {
  if (varType === 'array' && hasItems) {
    return <Badge variant="secondary" className="text-xs">array&lt;object&gt;</Badge>
  }
  return <Badge variant="secondary" className="text-xs">{varType || 'string'}</Badge>
}

function VariableSchemaRow({ varDef }: { varDef: VariableDefinition }) {
  const [expanded, setExpanded] = useState(false)
  const { t } = useTranslation()
  const hasSubFields = varDef.items_schema && varDef.items_schema.length > 0

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        {hasSubFields ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}
        <span className="font-medium text-sm">{varDef.name}</span>
        <TypeBadge varType={varDef.var_type} hasItems={!!hasSubFields} />
        {varDef.is_anchor && (
          <Badge variant="outline" className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
            {t('prompts.anchor')}
          </Badge>
        )}
      </div>

      {expanded && hasSubFields && (
        <div className="ml-7 mt-1 border-l-2 border-primary/20 pl-3 space-y-1">
          {varDef.items_schema!.map((subField, i) => (
            <div key={i} className="flex items-center gap-2 py-0.5">
              <span className="text-sm text-muted-foreground">{subField.name}</span>
              <Badge variant="secondary" className="text-xs">{subField.var_type || 'string'}</Badge>
              {!varDef.is_anchor && subField.is_anchor && (
                <Badge variant="outline" className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
                  {t('prompts.anchor')}
                </Badge>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PromptDetail({ promptId }: PromptDetailProps) {
  const { t } = useTranslation()
  const { data: prompt, isLoading, error } = useQuery({
    queryKey: ['prompts', promptId],
    queryFn: () =>
      getPromptApiPromptsPromptIdGet({
        path: { prompt_id: promptId },
      }),
  })

  if (isLoading) {
    return <PromptDetailSkeleton />
  }

  if (error) {
    return <p className="text-destructive">{t('prompts.failedToLoadPrompt')}</p>
  }

  const detail = prompt?.data
  if (!detail) {
    return <p className="text-muted-foreground">{t('prompts.promptNotFound')}</p>
  }

  const variableDefs = (detail.variable_definitions || []) as unknown as VariableDefinition[]

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader>
          <CardTitle>{detail.id}</CardTitle>
          <CardDescription>{detail.purpose}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            <div>
              <span className="text-sm text-muted-foreground block mb-1">{t('prompts.templateVariables')}</span>
              <div className="flex flex-wrap gap-1">
                {detail.template_variables.length > 0 ? (
                  detail.template_variables.map((v) => (
                    <Badge key={v} variant="secondary" className="bg-primary/20 text-primary border-primary/30">
                      {v}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">{t('prompts.none')}</span>
                )}
              </div>
            </div>

            <div>
              <span className="text-sm text-muted-foreground block mb-1">{t('prompts.anchorVariables')}</span>
              <div className="flex flex-wrap gap-1">
                {detail.anchor_variables.length > 0 ? (
                  detail.anchor_variables.map((v) => (
                    <Badge key={v} variant="outline" className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                      {v}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">{t('prompts.none')}</span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Variable Schema */}
      {variableDefs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">{t('prompts.variableSchema')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {variableDefs.map((varDef, i) => (
              <VariableSchemaRow key={i} varDef={varDef} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <Button variant="secondary" asChild>
          <Link to="../dataset">{t('prompts.viewTestCases')}</Link>
        </Button>
      </div>

      {/* Tools */}
      {detail.tools && detail.tools.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">{t('prompts.tools')}</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded bg-muted p-4 text-xs text-foreground">
              {JSON.stringify(detail.tools, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
