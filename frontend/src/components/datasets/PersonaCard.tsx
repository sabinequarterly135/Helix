import { useTranslation } from 'react-i18next'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Pencil, Trash2 } from 'lucide-react'

export interface Persona {
  id: string
  role: string
  traits: string[]
  communication_style: string
  goal: string
  edge_cases: string[]
  behavior_criteria: string[]
  language: string       // ISO 639-1 code, default "en"
  channel: string        // "text" or "voice", default "text"
}

interface PersonaCardProps {
  persona: Persona
  selected: boolean
  onToggleSelect: () => void
  onEdit: () => void
  onDelete: () => void
}

export function PersonaCard({ persona, selected, onToggleSelect, onEdit, onDelete }: PersonaCardProps) {
  const { t } = useTranslation()
  return (
    <Card
      className={`p-3 transition-colors ${selected ? 'border-primary bg-primary/5' : 'border-border'}`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          className="mt-1 h-4 w-4 rounded border-input accent-primary cursor-pointer"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-medium text-foreground truncate">{persona.role}</h4>
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                onClick={(e) => { e.stopPropagation(); onEdit() }}
                title={t('datasets.editPersona')}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete() }}
                title={t('datasets.deletePersona')}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
          {persona.traits.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {persona.traits.map((trait) => (
                <Badge key={trait} variant="secondary" className="text-[10px] px-1.5 py-0">
                  {trait}
                </Badge>
              ))}
            </div>
          )}
          {(persona.language && persona.language !== 'en') || persona.channel === 'voice' ? (
            <div className="flex flex-wrap gap-1 mt-1">
              {persona.language && persona.language !== 'en' && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  {persona.language}
                </Badge>
              )}
              {persona.channel === 'voice' && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  voice
                </Badge>
              )}
            </div>
          ) : null}
          {persona.goal && (
            <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">{persona.goal}</p>
          )}
        </div>
      </div>
    </Card>
  )
}
