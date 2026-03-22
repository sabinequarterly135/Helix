import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Editor from '@monaco-editor/react'
import jsYaml from 'js-yaml'
import { Clipboard, Check, Loader2, Sparkles, Save } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { generateTemplateApiWizardGeneratePost, createPromptApiPromptsPost } from '@/client/sdk.gen'
import type { WizardData } from './WizardFlow'

interface ReviewStepProps {
  data: WizardData
  yaml: string | null
  onYamlChange: (yaml: string | null) => void
}

/**
 * Parse a user-entered examples string into a list of values.
 * - For simple types (string, number, boolean): split by comma, trim, coerce types
 * - For complex types (object, array): try JSON.parse on each non-empty line
 * - Graceful degradation: unparseable values kept as raw strings
 */
function parseExamples(raw: string | undefined, varType: string): unknown[] | undefined {
  if (!raw || raw.trim() === '') return undefined

  if (varType === 'object' || varType === 'array') {
    const lines = raw.split('\n').filter((l) => l.trim() !== '')
    const results: unknown[] = []
    for (const line of lines) {
      try {
        results.push(JSON.parse(line.trim()))
      } catch {
        results.push(line.trim()) // graceful degradation
      }
    }
    return results.length > 0 ? results : undefined
  }

  // Simple types: comma-separated
  const parts = raw.split(',').map((s) => s.trim()).filter((s) => s !== '')
  if (parts.length === 0) return undefined

  return parts.map((part) => {
    if (varType === 'number') {
      const num = Number(part)
      return isNaN(num) ? part : num
    }
    if (varType === 'boolean') {
      if (part.toLowerCase() === 'true') return true
      if (part.toLowerCase() === 'false') return false
      return part
    }
    return part
  })
}

export function ReviewStep({ data, yaml, onYamlChange }: ReviewStepProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [registerError, setRegisterError] = useState<string | null>(null)

  const generateMutation = useMutation({
    mutationFn: () =>
      generateTemplateApiWizardGeneratePost({
        body: {
          id: data.id,
          purpose: data.purpose,
          description: data.description || undefined,
          variables: data.variables
            .filter((v) => v.name.trim() !== '')
            .map((v) => ({
              name: v.name,
              var_type: v.varType,
              description: v.description || undefined,
              is_anchor: v.isAnchor,
              examples: parseExamples(v.examples, v.varType),
              items_schema: v.itemsSchema
                ?.filter((sf) => sf.name.trim() !== '')
                .map((sf) => ({
                  name: sf.name,
                  var_type: sf.varType,
                  description: sf.description || undefined,
                  is_anchor: sf.isAnchor,
                })),
            })),
          constraints: data.constraints || undefined,
          behaviors: data.behaviors || undefined,
          include_tools: data.includeTools,
        },
      }),
    onSuccess: (result) => {
      if (result.data) {
        onYamlChange(result.data.yaml_template)
      }
    },
  })

  const registerMutation = useMutation({
    mutationFn: () => {
      // Parse the YAML to extract template content and variables
      // The wizard generates full YAML with id, purpose, template, variables fields
      // The API expects just the template text (Jinja2 prompt), not the YAML wrapper
      let templateText = yaml!
      let variables: Array<Record<string, unknown>> | undefined

      try {
        const parsed = jsYaml.load(yaml!) as Record<string, unknown> | null
        if (parsed && typeof parsed === 'object') {
          if (typeof parsed.template === 'string') {
            templateText = parsed.template
          }
          if (Array.isArray(parsed.variables)) {
            variables = parsed.variables as Array<Record<string, unknown>>
          }
        }
      } catch {
        // If YAML parsing fails, send raw text as template (best effort)
      }

      return createPromptApiPromptsPost({
        body: {
          id: data.id,
          purpose: data.purpose,
          template: templateText,
          variables: variables,
        },
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['prompts'] })
      navigate(`/prompts/${data.id}/template`)
    },
    onError: (error) => {
      setRegisterError(error instanceof Error ? error.message : 'Failed to register prompt')
    },
  })

  const handleCopy = async () => {
    if (!yaml) return
    try {
      await navigator.clipboard.writeText(yaml)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API not available
    }
  }

  const filteredVariables = data.variables.filter((v) => v.name.trim() !== '')

  return (
    <div className="space-y-4">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{t('wizard.review')}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="font-medium text-muted-foreground">{t('wizard.reviewId')}</dt>
            <dd className="text-foreground font-mono">{data.id}</dd>

            <dt className="font-medium text-muted-foreground">{t('wizard.reviewPurpose')}</dt>
            <dd className="text-foreground">{data.purpose}</dd>

            <dt className="font-medium text-muted-foreground">{t('wizard.reviewVariables')}</dt>
            <dd className="text-foreground">
              {filteredVariables.length === 0
                ? 'None'
                : filteredVariables.map((v) => (
                    <div key={v.name} className="text-sm">
                      <span className="font-mono">{v.name}</span>
                      <span className="text-muted-foreground ml-1">({v.varType})</span>
                      {v.examples && (
                        <span className="text-muted-foreground ml-1 text-xs">
                          — examples: {v.examples.length > 40 ? v.examples.slice(0, 40) + '...' : v.examples}
                        </span>
                      )}
                    </div>
                  ))}
            </dd>

            {data.constraints && (
              <>
                <dt className="font-medium text-muted-foreground">{t('wizard.reviewConstraints')}</dt>
                <dd className="text-foreground line-clamp-2">{data.constraints}</dd>
              </>
            )}

            {data.behaviors && (
              <>
                <dt className="font-medium text-muted-foreground">{t('wizard.reviewBehaviors')}</dt>
                <dd className="text-foreground line-clamp-2">{data.behaviors}</dd>
              </>
            )}
          </dl>
        </CardContent>
      </Card>

      {/* Generate Button */}
      <Button
        onClick={() => generateMutation.mutate()}
        disabled={generateMutation.isPending}
        className="w-full"
        size="lg"
      >
        {generateMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Generating template...
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4 mr-2" />
            Generate Template
          </>
        )}
      </Button>

      {generateMutation.isError && (
        <p className="text-sm text-destructive">
          Failed to generate template. Please try again.
        </p>
      )}

      {/* YAML Preview */}
      {yaml && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-lg">{t('wizard.generatedTemplate')}</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4 mr-1" />
                  Copied!
                </>
              ) : (
                <>
                  <Clipboard className="h-4 w-4 mr-1" />
                  Copy
                </>
              )}
            </Button>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border border-border overflow-hidden">
              <Editor
                height="400px"
                language="yaml"
                value={yaml}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  fontSize: 13,
                  lineNumbers: 'on',
                  wordWrap: 'on',
                }}
                theme="vs-dark"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Register Button */}
      {yaml && (
        <Button
          onClick={() => {
            setRegisterError(null)
            registerMutation.mutate()
          }}
          disabled={registerMutation.isPending}
          variant="secondary"
          className="w-full"
          size="lg"
        >
          {registerMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Registering...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              Register Prompt
            </>
          )}
        </Button>
      )}

      {registerError && (
        <p className="text-sm text-destructive">{registerError}</p>
      )}
    </div>
  )
}
