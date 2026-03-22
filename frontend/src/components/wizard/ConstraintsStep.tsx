import { useTranslation } from 'react-i18next'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import type { WizardData } from './WizardFlow'

interface ConstraintsStepProps {
  data: WizardData
  onChange: (data: WizardData) => void
}

export function ConstraintsStep({ data, onChange }: ConstraintsStepProps) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{t('wizard.constraints')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="wizard-constraints" className="text-sm font-medium text-foreground">
            {t('wizard.constraintsLabel')}
          </label>
          <Textarea
            id="wizard-constraints"
            placeholder={t('wizard.constraintsPlaceholder')}
            value={data.constraints}
            onChange={(e) => onChange({ ...data, constraints: e.target.value })}
            rows={4}
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="wizard-behaviors" className="text-sm font-medium text-foreground">
            {t('wizard.expectedBehaviors')}
          </label>
          <Textarea
            id="wizard-behaviors"
            placeholder={t('wizard.expectedBehaviorsPlaceholder')}
            value={data.behaviors}
            onChange={(e) => onChange({ ...data, behaviors: e.target.value })}
            rows={4}
          />
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Switch
            id="wizard-tools"
            checked={data.includeTools}
            onCheckedChange={(checked) =>
              onChange({ ...data, includeTools: checked })
            }
          />
          <label htmlFor="wizard-tools" className="text-sm font-medium text-foreground cursor-pointer">
            {t('wizard.usesToolCalling')}
          </label>
        </div>

        {data.includeTools && (
          <div className="space-y-2">
            <label htmlFor="wizard-tool-descriptions" className="text-sm font-medium text-foreground">
              {t('wizard.toolDescriptions')}
            </label>
            <Textarea
              id="wizard-tool-descriptions"
              placeholder={t('wizard.toolDescriptionsPlaceholder')}
              value={data.toolDescriptions}
              onChange={(e) => onChange({ ...data, toolDescriptions: e.target.value })}
              rows={4}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
